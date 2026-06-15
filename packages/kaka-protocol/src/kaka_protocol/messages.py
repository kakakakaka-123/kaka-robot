from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from kaka_protocol.enums import ContentType, Platform, SceneType


class MessageContent(BaseModel):
    """统一后的消息内容。

    不同平台的原始内容会被适配器转换成这个结构。
    例如 QQ 文本、网页输入、语音识别结果都可以统一成文本内容。
    """

    # 内容类型，例如文本、图片、语音或传感器数据。
    type: ContentType

    # 文本内容。第一阶段最常用的字段。
    text: str | None = None

    # 媒体资源地址。后续图片、语音、视频会用到。
    media_url: str | None = None

    # 媒体 MIME 类型，例如图片 PNG 或音频 WAV。
    mime_type: str | None = None

    # 结构化附加数据。传感器读数、平台扩展字段等可以放这里。
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def text_message(cls, text: str) -> "MessageContent":
        return cls(type=ContentType.TEXT, text=text)


class MessageEvent(BaseModel):
    """适配器发送给卡咔核心服务的统一输入事件。

    QQ、网页、语音、物联网设备的原始事件都应该先转换成 MessageEvent，
    这样卡咔核心服务就不需要关心外部平台的细节。
    """

    # 事件唯一标识。默认自动生成，方便日志追踪和回复关联。
    event_id: str = Field(default_factory=lambda: str(uuid4()))

    # 来源平台，例如 QQ、网页、语音或物联网设备。
    platform: Platform

    # 场景类型，例如私聊、群聊、房间或设备。
    scene_type: SceneType

    # 场景标识。QQ 群聊可用群号，私聊可用用户 QQ 号。
    scene_id: str

    # 用户稳定标识。权限、记忆和关系判断应该优先使用这个字段。
    user_id: str

    # 统一后的消息内容。
    content: MessageContent

    # 当前显示名。它可以变化，不能作为长期身份主键。
    display_name: str | None = None

    # 事件发生时间，默认使用协调世界时。
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 原始平台事件。用于调试或后续补充字段，不建议核心逻辑直接依赖。
    raw_event: dict[str, Any] = Field(default_factory=dict)

    # 协议级额外信息，例如适配器版本、消息来源补充标记等。
    metadata: dict[str, Any] = Field(default_factory=dict)
