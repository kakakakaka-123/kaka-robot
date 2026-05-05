from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

from sqlalchemy import func, select

from kaka_core.config.settings import MemoryReviewSettings, get_settings
from kaka_core.llm.router import LLMRouter
from kaka_core.memory.auto_jobs import (
    AUTO_JOB_STATUS_FAILED,
    AUTO_JOB_STATUS_SKIPPED,
    AUTO_JOB_STATUS_SUCCESS,
    AutoJobRunData,
    record_auto_job_run_safely,
)
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.models import MemoryCandidateRecord, utc_now

AUTO_REVIEW_JOB_NAME = "auto_review"


@dataclass
class AutoReviewRunSummary:
    checked_count: int
    ran: bool
    reason: str
    processed_runs: int = 0
    approved: int = 0
    rejected: int = 0
    duplicates: int = 0
    errors: int = 0


@dataclass
class AutoReviewScheduler:
    settings: MemoryReviewSettings
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stopped: asyncio.Event = field(default_factory=asyncio.Event)

    def start(self) -> None:
        if not self.settings.enabled:
            print("自动候选区 LLM 复核未启用。")
            return
        if self.task is not None and not self.task.done():
            return
        self.stopped.clear()
        self.task = asyncio.create_task(self.run_forever())
        print(
            "自动候选区 LLM 复核已启用：每个整点检查一次；"
            f"pending >= {self.settings.trigger_count} 时触发。"
        )

    async def stop(self) -> None:
        self.stopped.set()
        if self.task is None:
            return
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass

    async def run_forever(self) -> None:
        while not self.stopped.is_set():
            delay = seconds_until_next_hour()
            try:
                await asyncio.wait_for(self.stopped.wait(), timeout=delay)
                break
            except TimeoutError:
                pass

            if self.lock.locked():
                print("自动候选区 LLM 复核仍在运行，本次整点检查跳过。")
                continue

            async with self.lock:
                try:
                    summary = await run_auto_review_check_and_record(self.settings)
                    print(format_auto_review_summary(summary))
                except Exception as exc:  # noqa: BLE001
                    print(f"自动候选区 LLM 复核失败：{exc}")


def seconds_until_next_hour(now: datetime | None = None) -> float:
    current = now or datetime.now().astimezone()
    next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return max(0.0, (next_hour - current).total_seconds())


async def run_auto_review_check(
    settings: MemoryReviewSettings | None = None,
) -> AutoReviewRunSummary:
    config = settings or get_settings().memory_review
    trigger_count = max(1, config.trigger_count)
    batch_size = max(1, config.batch_size)
    max_runs_per_check = max(1, config.max_runs_per_check)

    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        pending_count = count_pending_candidates(session)

    if pending_count < trigger_count:
        return AutoReviewRunSummary(
            checked_count=pending_count,
            ran=False,
            reason=f"未达到触发门槛 {trigger_count}",
        )

    llm_settings = get_settings().llm
    if not llm_settings.can_call_remote:
        return AutoReviewRunSummary(
            checked_count=pending_count,
            ran=False,
            reason="LLM 未启用或缺少 LLM_API_KEY",
        )

    review_candidates = load_review_candidates_module()
    router = LLMRouter(llm_settings)
    summary = AutoReviewRunSummary(
        checked_count=pending_count,
        ran=True,
        reason="已执行",
    )

    for _ in range(max_runs_per_check):
        with session_factory() as session:
            filters = review_candidates.ReviewFilters(
                limit=batch_size,
                batch_size=batch_size,
                status=review_candidates.CANDIDATE_STATUS_PENDING,
                apply=True,
            )
            rows = review_candidates.load_review_rows(session, filters)
            if not rows:
                break

            existing_keys = review_candidates.load_existing_memory_keys(
                session,
                {row.user.id for row in rows},
            )
            decisions = await review_candidates.review_rows(
                rows,
                router,
                batch_size,
                existing_keys,
            )
            stats = review_candidates.apply_decisions(session, decisions)
            session.commit()

        summary.processed_runs += 1
        summary.approved += stats.approved
        summary.rejected += stats.rejected
        summary.duplicates += stats.duplicates
        summary.errors += stats.errors

    if summary.processed_runs == 0:
        summary.ran = False
        summary.reason = "没有可处理候选"
    return summary


async def run_auto_review_check_and_record(
    settings: MemoryReviewSettings | None = None,
) -> AutoReviewRunSummary:
    started_at = utc_now()
    try:
        summary = await run_auto_review_check(settings)
    except Exception as exc:
        finished_at = utc_now()
        record_error = record_auto_job_run_safely(
            AutoJobRunData(
                job_name=AUTO_REVIEW_JOB_NAME,
                status=AUTO_JOB_STATUS_FAILED,
                reason="执行异常",
                error_count=1,
                error_message=str(exc),
                started_at=started_at,
                finished_at=finished_at,
            )
        )
        if record_error:
            print(f"自动候选区 LLM 复核运行记录写入失败：{record_error}")
        raise

    finished_at = utc_now()
    record_error = record_auto_job_run_safely(
        auto_review_summary_to_job_run(summary, started_at, finished_at)
    )
    if record_error:
        print(f"自动候选区 LLM 复核运行记录写入失败：{record_error}")
    return summary


def auto_review_summary_to_job_run(
    summary: AutoReviewRunSummary,
    started_at: datetime,
    finished_at: datetime,
) -> AutoJobRunData:
    return AutoJobRunData(
        job_name=AUTO_REVIEW_JOB_NAME,
        status=AUTO_JOB_STATUS_SUCCESS if summary.ran else AUTO_JOB_STATUS_SKIPPED,
        reason=summary.reason,
        checked_count=summary.checked_count,
        processed_runs=summary.processed_runs,
        inserted_count=summary.approved,
        updated_count=summary.rejected + summary.duplicates,
        skipped_count=0,
        error_count=summary.errors,
        metadata={
            "approved": summary.approved,
            "rejected": summary.rejected,
            "duplicates": summary.duplicates,
        },
        started_at=started_at,
        finished_at=finished_at,
    )


def count_pending_candidates(session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(MemoryCandidateRecord).where(
                MemoryCandidateRecord.status == "pending"
            )
        )
        or 0
    )


def load_review_candidates_module() -> ModuleType:
    root = Path(__file__).resolve().parents[5]
    script_path = root / "services" / "kaka-core" / "scripts" / "review_memory_candidates.py"
    module_name = "kaka_core_memory_auto_review_candidates"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载候选复核脚本：{script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def format_auto_review_summary(summary: AutoReviewRunSummary) -> str:
    if not summary.ran:
        return (
            "自动候选区 LLM 复核跳过："
            f"{summary.reason}；当前 pending={summary.checked_count}"
        )
    return (
        "自动候选区 LLM 复核完成："
        f"启动时 pending={summary.checked_count}；"
        f"执行轮数={summary.processed_runs}；"
        f"approved={summary.approved}；"
        f"rejected={summary.rejected}；"
        f"duplicates={summary.duplicates}；"
        f"errors={summary.errors}"
    )


def create_auto_review_scheduler() -> AutoReviewScheduler:
    return AutoReviewScheduler(settings=get_settings().memory_review)
