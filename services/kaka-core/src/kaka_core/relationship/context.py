from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from kaka_core.config.settings import RelationshipSettings
from kaka_protocol import MessageEvent

RelationshipLevel = Literal["special", "normal"]


@dataclass(frozen=True)
class RelationshipContext:
    """当前说话者和卡咔的粗略关系上下文。

    关系层只区分创造者大人和普通群友；熟悉感交给短期上下文和长期记忆自然表达。
    """

    level: RelationshipLevel
    is_owner: bool


def load_relationship_context(
    session: Session | None,
    event: MessageEvent,
    settings: RelationshipSettings,
) -> RelationshipContext:
    """基于配置判断当前说话者是否是特殊关系。

    保留 session 参数是为了兼容上下文构建入口；当前两档关系不再读取互动次数或记忆数量。
    """

    _ = session
    is_owner = event.user_id in settings.owner_user_ids
    return RelationshipContext(
        level="special" if is_owner else "normal",
        is_owner=is_owner,
    )
