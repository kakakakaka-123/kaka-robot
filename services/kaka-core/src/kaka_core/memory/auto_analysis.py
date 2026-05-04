from __future__ import annotations

import asyncio
import importlib.util
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

from sqlalchemy import func, select

from kaka_core.config.settings import MemoryAnalysisSettings, get_settings
from kaka_core.llm.router import LLMRouter
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.models import InputRecord


@dataclass
class AutoAnalysisRunSummary:
    checked_count: int
    ran: bool
    reason: str
    processed_runs: int = 0
    candidates_inserted: int = 0
    skipped_marked: int = 0
    analyzed_marked: int = 0
    llm_errors_left_unprocessed: int = 0
    missing_llm_results: int = 0


@dataclass
class AutoAnalysisScheduler:
    settings: MemoryAnalysisSettings
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    stopped: asyncio.Event = field(default_factory=asyncio.Event)

    def start(self) -> None:
        if not self.settings.enabled:
            print("自动记忆候选分析未启用。")
            return
        if self.task is not None and not self.task.done():
            return
        self.stopped.clear()
        self.task = asyncio.create_task(self.run_forever())
        if self.settings.interval_seconds > 0:
            print(f"自动记忆候选分析已启用：每 {self.settings.interval_seconds} 秒检查一次。")
        else:
            print("自动记忆候选分析已启用：每个整点检查一次。")

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
            delay = next_check_delay(self.settings)
            try:
                await asyncio.wait_for(self.stopped.wait(), timeout=delay)
                break
            except TimeoutError:
                pass

            if self.lock.locked():
                print("自动记忆候选分析仍在运行，本次整点检查跳过。")
                continue

            async with self.lock:
                try:
                    summary = await run_auto_analysis_check(self.settings)
                    print(format_auto_analysis_summary(summary))
                except Exception as exc:  # noqa: BLE001
                    print(f"自动记忆候选分析失败：{exc}")


def seconds_until_next_hour(now: datetime | None = None) -> float:
    current = now or datetime.now().astimezone()
    next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return max(0.0, (next_hour - current).total_seconds())


def next_check_delay(settings: MemoryAnalysisSettings, now: datetime | None = None) -> float:
    if settings.interval_seconds > 0:
        return float(settings.interval_seconds)
    return seconds_until_next_hour(now)


async def run_auto_analysis_check(
    settings: MemoryAnalysisSettings | None = None,
) -> AutoAnalysisRunSummary:
    config = settings or get_settings().memory_analysis
    trigger_count = max(1, config.trigger_count)
    batch_limit = max(1, config.batch_limit)
    max_runs_per_check = max(1, config.max_runs_per_check)
    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        pending_count = count_not_analyzed_inputs(session)

    if pending_count < trigger_count:
        return AutoAnalysisRunSummary(
            checked_count=pending_count,
            ran=False,
            reason=f"未达到触发门槛 {trigger_count}",
        )

    llm_settings = get_settings().llm
    if not llm_settings.can_call_remote:
        return AutoAnalysisRunSummary(
            checked_count=pending_count,
            ran=False,
            reason="LLM 未启用或缺少 LLM_API_KEY",
        )

    analyze_inputs = load_analyze_inputs_module()
    router = LLMRouter(llm_settings)
    summary = AutoAnalysisRunSummary(
        checked_count=pending_count,
        ran=True,
        reason="已执行",
    )

    for _ in range(max_runs_per_check):
        with session_factory() as session:
            current_count = count_not_analyzed_inputs(session)
            if current_count < trigger_count:
                break

            filters = analyze_inputs.AnalysisFilters(
                limit=batch_limit,
                use_llm_batch=True,
                write_candidates=True,
            )
            rows = analyze_inputs.load_unanalyzed_inputs(session, filters)
            if not rows:
                break

            classified_rows = analyze_inputs.classify_rows(rows)
            batches = analyze_inputs.build_llm_batches(classified_rows)
            batch_stats = analyze_inputs.BatchLLMStats()
            batch_results = await analyze_inputs.analyze_llm_batches(
                batches,
                router,
                batch_stats,
            )
            write_stats = analyze_inputs.write_candidates_and_mark_inputs(
                session,
                classified_rows,
                batch_results,
                analysis_model=llm_settings.memory_model,
                analysis_prompt_version=analyze_inputs.LLM_BATCH_ANALYSIS_PROMPT_VERSION,
            )
            session.commit()

        summary.processed_runs += 1
        summary.candidates_inserted += write_stats.total_candidates_inserted
        summary.skipped_marked += write_stats.total_skipped_marked
        summary.analyzed_marked += write_stats.analyzed_marked
        summary.llm_errors_left_unprocessed += write_stats.llm_errors_left_unprocessed
        summary.missing_llm_results += write_stats.missing_llm_results

    if summary.processed_runs == 0:
        summary.ran = False
        summary.reason = "没有可处理记录"
    return summary


def count_not_analyzed_inputs(session) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(InputRecord).where(
                InputRecord.analysis_status == "not_analyzed"
            )
        )
        or 0
    )


def load_analyze_inputs_module() -> ModuleType:
    root = Path(__file__).resolve().parents[5]
    script_path = root / "services" / "kaka-core" / "scripts" / "analyze_inputs.py"
    module_name = "kaka_core_memory_auto_analyze_inputs"
    cached = sys.modules.get(module_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载分析脚本：{script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def format_auto_analysis_summary(summary: AutoAnalysisRunSummary) -> str:
    if not summary.ran:
        return (
            "自动记忆候选分析跳过："
            f"{summary.reason}；当前 not_analyzed={summary.checked_count}"
        )
    return (
        "自动记忆候选分析完成："
        f"启动时 not_analyzed={summary.checked_count}；"
        f"执行轮数={summary.processed_runs}；"
        f"新增候选={summary.candidates_inserted}；"
        f"标记 skipped={summary.skipped_marked}；"
        f"标记 analyzed={summary.analyzed_marked}；"
        f"LLM error 保持未处理={summary.llm_errors_left_unprocessed}；"
        f"缺少 LLM 结果={summary.missing_llm_results}"
    )


def create_auto_analysis_scheduler() -> AutoAnalysisScheduler:
    return AutoAnalysisScheduler(settings=get_settings().memory_analysis)
