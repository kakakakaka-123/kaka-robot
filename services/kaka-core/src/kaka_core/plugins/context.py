from dataclasses import dataclass, field
from typing import Any

from kaka_protocol import MessageEvent


@dataclass(frozen=True)
class PluginContext:
    """插件运行时看到的统一上下文。

    这里故意只暴露跨平台字段，不暴露 QQ、桌宠或其他适配器原始对象。
    """

    event_id: str
    platform: str
    scene_type: str
    scene_id: str
    user_id: str
    display_name: str | None
    text: str
    content_type: str
    command_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_event(cls, event: MessageEvent, *, command_text: str = "") -> "PluginContext":
        return cls(
            event_id=event.event_id,
            platform=str(event.platform),
            scene_type=str(event.scene_type),
            scene_id=event.scene_id,
            user_id=event.user_id,
            display_name=event.display_name,
            text=event.content.text or "",
            content_type=str(event.content.type),
            command_text=command_text,
            metadata=dict(event.metadata),
        )
