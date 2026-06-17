from dataclasses import dataclass
from typing import Any

from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType


@dataclass(frozen=True)
class QQTextEvent:
    """适配器内部使用的 QQ 文本事件。

    这个结构不是最终协议，只是为了把 QQ 原始字典先整理干净。
    后续接入 NoneBot 后，也可以从 NoneBot 事件转成这个结构。
    """

    message_id: str
    scene_type: SceneType
    scene_id: str
    user_id: str
    display_name: str | None
    text: str
    raw_event: dict[str, Any]


def parse_onebot_text_event(raw_event: dict[str, Any]) -> QQTextEvent:
    """解析 OneBot 风格的 QQ 文本事件。

    当前只处理最小文本消息：
    - private：私聊
    - group：群聊

    后续图片、表情、语音等消息会在这里继续扩展。
    """

    post_type = raw_event.get("post_type")
    message_type = raw_event.get("message_type")
    if post_type != "message":
        raise ValueError(f"暂不支持的 post_type：{post_type}")
    if message_type not in {"private", "group"}:
        raise ValueError(f"暂不支持的 message_type：{message_type}")

    text = _extract_plain_text(raw_event.get("message"))
    if not text:
        raise ValueError("当前只支持非空文本消息。")

    user_id = str(raw_event["user_id"])
    message_id = str(raw_event.get("message_id", ""))
    sender = raw_event.get("sender") or {}
    display_name = sender.get("card") or sender.get("nickname")

    if message_type == "group":
        scene_type = SceneType.GROUP
        scene_id = str(raw_event["group_id"])
    else:
        scene_type = SceneType.PRIVATE
        scene_id = user_id

    return QQTextEvent(
        message_id=message_id,
        scene_type=scene_type,
        scene_id=scene_id,
        user_id=user_id,
        display_name=display_name,
        text=text,
        raw_event=raw_event,
    )


def qq_text_event_to_message_event(event: QQTextEvent) -> MessageEvent:
    """把 QQ 文本事件转换成项目统一消息事件。"""

    payload = {
        "platform": Platform.QQ,
        "scene_type": event.scene_type,
        "scene_id": event.scene_id,
        "user_id": event.user_id,
        "display_name": event.display_name,
        "content": MessageContent.text_message(event.text),
        "raw_event": event.raw_event,
        "metadata": {"qq_message_id": event.message_id},
    }
    # message_id 为空时合成一个稳定 event_id，保证去重路径仍能工作。
    payload["event_id"] = build_qq_event_id(event)

    return MessageEvent(**payload)


def build_qq_event_id(event: QQTextEvent) -> str:
    """用 QQ 消息 ID 构造稳定事件标识，避免重启或重发后重复入库。"""

    return f"qq:{event.scene_type}:{event.scene_id}:{event.message_id}"


def onebot_event_to_message_event(raw_event: dict[str, Any]) -> MessageEvent:
    """从 OneBot 原始事件一步转换成统一消息事件。"""

    return qq_text_event_to_message_event(parse_onebot_text_event(raw_event))


def _extract_plain_text(message: Any) -> str:
    """从 OneBot 消息字段中提取纯文本。

    OneBot 的 message 可能是字符串，也可能是消息段列表。
    第一版先只抽取 text 段，其他段后续再扩展。
    """

    if isinstance(message, str):
        return message.strip()

    if isinstance(message, list):
        text_parts: list[str] = []
        for segment in message:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") != "text":
                continue
            data = segment.get("data") or {}
            text = data.get("text")
            if isinstance(text, str):
                text_parts.append(text)
        return "".join(text_parts).strip()

    return ""
