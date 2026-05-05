from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.models import AutoJobRunRecord, utc_now
from kaka_core.storage.repository import (
    release_event_processing_lock,
    try_acquire_event_processing_lock,
)

AUTO_JOB_STATUS_SUCCESS = "success"
AUTO_JOB_STATUS_SKIPPED = "skipped"
AUTO_JOB_STATUS_FAILED = "failed"
AUTO_JOB_LOCK_LEASE_SECONDS = 3600
AUTO_JOB_LOCK_PREFIX = "auto_job:"


@dataclass(frozen=True)
class AutoJobRunData:
    """自动后台任务的一次运行结果。"""

    job_name: str
    status: str
    reason: str
    checked_count: int = 0
    processed_runs: int = 0
    inserted_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


def record_auto_job_run(data: AutoJobRunData) -> None:
    """记录自动任务运行结果。

    记录失败不应该影响自动任务主流程，因此调用方会捕获这里抛出的异常。
    """

    init_database()
    now = utc_now()
    session_factory = create_session_factory()
    with session_factory() as session:
        session.add(
            AutoJobRunRecord(
                job_name=data.job_name,
                status=data.status,
                reason=data.reason,
                checked_count=max(0, data.checked_count),
                processed_runs=max(0, data.processed_runs),
                inserted_count=max(0, data.inserted_count),
                updated_count=max(0, data.updated_count),
                skipped_count=max(0, data.skipped_count),
                error_count=max(0, data.error_count),
                error_message=data.error_message,
                extra_metadata=dict(data.metadata),
                started_at=data.started_at or now,
                finished_at=data.finished_at or now,
                created_at=now,
            )
        )
        session.commit()


def record_auto_job_run_safely(data: AutoJobRunData) -> str | None:
    try:
        record_auto_job_run(data)
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return None


def acquire_auto_job_lock_safely(job_name: str) -> tuple[str | None, str | None]:
    """获取跨进程自动任务锁。

    返回 (owner_token, None) 表示拿到锁；返回 (None, None) 表示已有任务在运行；
    返回 (None, error) 表示锁本身读写失败。
    """

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            owner_token = try_acquire_event_processing_lock(
                session,
                auto_job_lock_id(job_name),
                lease_seconds=AUTO_JOB_LOCK_LEASE_SECONDS,
            )
            return owner_token, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def release_auto_job_lock_safely(job_name: str, owner_token: str) -> str | None:
    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            release_event_processing_lock(session, auto_job_lock_id(job_name), owner_token)
    except Exception as exc:  # noqa: BLE001
        return str(exc)
    return None


def auto_job_lock_id(job_name: str) -> str:
    return f"{AUTO_JOB_LOCK_PREFIX}{job_name}"
