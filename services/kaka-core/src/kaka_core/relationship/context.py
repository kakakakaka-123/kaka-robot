from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session

from kaka_core.config.settings import RelationshipSettings
from kaka_protocol import MessageEvent

RelationshipLevel = Literal["special", "normal"]


@dataclass(frozen=True)
class RelationshipContext:
    """Lightweight relationship hint for the current speaker."""

    level: RelationshipLevel
    is_owner: bool


def load_relationship_context(
    session: Session | None,
    event: MessageEvent,
    settings: RelationshipSettings,
) -> RelationshipContext:
    """Mark configured user IDs as special without platform-specific coupling."""

    _ = session
    is_owner = event.user_id in settings.owner_user_ids
    return RelationshipContext(
        level="special" if is_owner else "normal",
        is_owner=is_owner,
    )
