"""卡咔 的统一协议模型。

这个包会被两类模块共同使用：
- adapter：QQ、网页、语音、IoT 等外部入口。
- kaka-core：卡咔的核心大脑。

协议层只负责定义数据格式，不负责连接平台、调用模型或保存数据库。
"""

from kaka_protocol.enums import ActionType, ContentType, Platform, SceneType
from kaka_protocol.messages import MessageContent, MessageEvent
from kaka_protocol.responses import KakaResponse, ResponseAction

__all__ = [
    "ActionType",
    "ContentType",
    "KakaResponse",
    "MessageContent",
    "MessageEvent",
    "Platform",
    "ResponseAction",
    "SceneType",
]
