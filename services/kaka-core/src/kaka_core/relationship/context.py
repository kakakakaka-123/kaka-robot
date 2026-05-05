from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from kaka_core.config.settings import RelationshipSettings
from kaka_core.storage.models import InputRecord, MemoryRecord, UserRecord, utc_now
from kaka_protocol import MessageEvent

RelationshipLevel = Literal["owner", "familiar", "regular", "stranger"]


@dataclass(frozen=True)
class RelationshipContext:
    """当前说话者和卡咔的粗略关系上下文。

    这里只使用现有数据库里的可回查信号：互动次数、近期出现次数和正式记忆数量。
    不引入好感度分数，避免把熟悉、信任和亲近混在一起。
    """

    level: RelationshipLevel
    is_owner: bool
    input_count: int
    recent_input_count: int
    active_memory_count: int
    recent_days: int


def load_relationship_context(
    session: Session,
    event: MessageEvent,
    settings: RelationshipSettings,
) -> RelationshipContext:
    """基于现有记录推断当前说话者的熟悉度。"""

    user = session.scalar(
        select(UserRecord).where(
            UserRecord.platform == str(event.platform),
            UserRecord.platform_user_id == event.user_id,
        )
    )
    is_owner = event.user_id in settings.owner_user_ids
    if user is None:
        return RelationshipContext(
            level="owner" if is_owner else "stranger",
            is_owner=is_owner,
            input_count=0,
            recent_input_count=0,
            active_memory_count=0,
            recent_days=max(1, settings.recent_days),
        )

    recent_days = max(1, settings.recent_days)
    recent_threshold = utc_now() - timedelta(days=recent_days)
    input_count = count_user_inputs(session, user.id)
    recent_input_count = count_user_inputs(session, user.id, since=recent_threshold)
    active_memory_count = count_active_memories(session, user.id)

    return RelationshipContext(
        level=decide_relationship_level(
            is_owner=is_owner,
            input_count=input_count,
            recent_input_count=recent_input_count,
            active_memory_count=active_memory_count,
            settings=settings,
        ),
        is_owner=is_owner,
        input_count=input_count,
        recent_input_count=recent_input_count,
        active_memory_count=active_memory_count,
        recent_days=recent_days,
    )


def decide_relationship_level(
    *,
    is_owner: bool,
    input_count: int,
    recent_input_count: int,
    active_memory_count: int,
    settings: RelationshipSettings,
) -> RelationshipLevel:
    if is_owner:
        return "owner"
    if (
        input_count >= settings.familiar_input_count
        or recent_input_count >= settings.familiar_recent_input_count
        or active_memory_count >= settings.familiar_active_memory_count
    ):
        return "familiar"
    if (
        input_count >= settings.regular_input_count
        or recent_input_count >= settings.regular_recent_input_count
        or active_memory_count >= settings.regular_active_memory_count
    ):
        return "regular"
    return "stranger"


def count_user_inputs(session: Session, user_id: int, *, since=None) -> int:
    statement = select(func.count()).select_from(InputRecord).where(InputRecord.user_id == user_id)
    if since is not None:
        statement = statement.where(InputRecord.created_at >= since)
    return int(session.scalar(statement) or 0)


def count_active_memories(session: Session, user_id: int) -> int:
    return int(
        session.scalar(
            select(func.count()).select_from(MemoryRecord).where(
                MemoryRecord.user_id == user_id,
                MemoryRecord.status == "active",
            )
        )
        or 0
    )
