from typing import Any

from pydantic import BaseModel, Field

from kaka_protocol.enums import Platform, SceneType
from kaka_protocol.messages import MessageContent


class NotificationTarget(BaseModel):
    """A platform-neutral target for proactive outbound messages."""

    platform: Platform
    scene_type: SceneType
    scene_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationRequest(BaseModel):
    """A proactive notification request from an external workflow or core service."""

    target: NotificationTarget
    content: MessageContent
    source: str = "external"
    idempotency_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationResult(BaseModel):
    """Delivery result for a proactive notification."""

    accepted: bool
    delivered: bool = False
    target: NotificationTarget
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
