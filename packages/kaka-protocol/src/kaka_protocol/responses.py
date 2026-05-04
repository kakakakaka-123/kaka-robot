from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from kaka_protocol.enums import ActionType, ContentType
from kaka_protocol.messages import MessageContent


class ResponseAction(BaseModel):
    """卡咔核心服务返回给适配器的一条执行动作。

    一个回复里可以包含多个动作，例如先发文字，再发图片。
    第一阶段主要使用发送文本动作。
    """

    # 动作类型，例如发送文本、发送图片或不执行动作。
    type: ActionType

    # 动作携带的内容。不执行动作或部分工具动作可以为空。
    content: MessageContent | None = None

    # 目标场景标识。为空时通常由适配器默认发回原始场景。
    target_scene_id: str | None = None

    # 动作额外信息，例如平台特定发送参数。
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def send_text(cls, text: str, target_scene_id: str | None = None) -> "ResponseAction":
        return cls(
            type=ActionType.SEND_TEXT,
            content=MessageContent(type=ContentType.TEXT, text=text),
            target_scene_id=target_scene_id,
        )

    @classmethod
    def noop(cls, reason: str | None = None) -> "ResponseAction":
        metadata = {"reason": reason} if reason else {}
        return cls(type=ActionType.NOOP, metadata=metadata)


class KakaResponse(BaseModel):
    """卡咔核心服务返回给适配器的统一响应。

    它描述卡咔是否要回复，以及需要适配器执行哪些动作。
    """

    # 回复唯一标识。用于日志、调试和后续追踪。
    response_id: str = Field(default_factory=lambda: str(uuid4()))

    # 对应的输入事件标识，方便把输入和输出关联起来。
    event_id: str | None = None

    # 是否需要回复。群聊里没被提到时，可能为否。
    should_reply: bool = True

    # 适配器需要执行的动作列表。
    actions: list[ResponseAction] = Field(default_factory=list)

    # 响应创建时间，默认使用协调世界时。
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 响应额外信息，例如不回复原因、调试标记等。
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def text_reply(cls, text: str, event_id: str | None = None) -> "KakaResponse":
        return cls(event_id=event_id, actions=[ResponseAction.send_text(text)])

    @classmethod
    def no_reply(cls, event_id: str | None = None, reason: str | None = None) -> "KakaResponse":
        metadata = {"reason": reason} if reason else {}
        return cls(event_id=event_id, should_reply=False, actions=[], metadata=metadata)
