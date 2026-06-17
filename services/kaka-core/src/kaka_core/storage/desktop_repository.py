"""桌面操作相关的数据库操作。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from kaka_core.storage.models import DesktopOperationRecord, utc_now


def create_desktop_operation(
    session: Session,
    *,
    operation_type: str,
    params: dict,
    requester_user_id: str,
    requester_scene_id: str,
    requester_platform: str,
    requester_scene_type: str = "private",
    approved: bool = True,
    decision_reason: str | None = None,
    kaka_mood: str | None = None,
    permission_level: int = 1,
) -> int:
    """创建桌面操作任务。

    返回操作 ID。
    """
    record = DesktopOperationRecord(
        operation_type=operation_type,
        params=params,
        requester_user_id=requester_user_id,
        requester_scene_id=requester_scene_id,
        requester_scene_type=requester_scene_type,
        requester_platform=requester_platform,
        approved=approved,
        decision_reason=decision_reason,
        kaka_mood=kaka_mood,
        permission_level=permission_level,
        status="pending",
        created_at=utc_now(),
    )
    session.add(record)
    session.flush()
    return record.id


def get_pending_operations(
    session: Session,
    limit: int = 10,
) -> list[DesktopOperationRecord]:
    """获取待执行的操作（供本地组件轮询）。

    只返回 status=pending 且 approved=True 的操作。
    """
    stmt = (
        select(DesktopOperationRecord)
        .where(
            DesktopOperationRecord.status == "pending",
            DesktopOperationRecord.approved == True,  # noqa: E712
        )
        .order_by(DesktopOperationRecord.created_at)
        .limit(limit)
    )
    return list(session.scalars(stmt))


def mark_operation_executing(
    session: Session,
    operation_id: int,
) -> None:
    """标记操作正在执行。"""
    record = session.get(DesktopOperationRecord, operation_id)
    if record:
        record.status = "executing"
        record.started_at = utc_now()


def complete_operation(
    session: Session,
    operation_id: int,
    *,
    success: bool,
    result: dict,
) -> DesktopOperationRecord | None:
    """完成操作并记录结果。"""
    record = session.get(DesktopOperationRecord, operation_id)
    if not record:
        return None

    record.status = "completed" if success else "failed"
    record.result = result
    record.completed_at = utc_now()

    if not success and result.get("error"):
        record.error_message = result["error"]

    return record


def get_operation_by_id(
    session: Session,
    operation_id: int,
) -> DesktopOperationRecord | None:
    """查询操作详情。"""
    return session.get(DesktopOperationRecord, operation_id)
