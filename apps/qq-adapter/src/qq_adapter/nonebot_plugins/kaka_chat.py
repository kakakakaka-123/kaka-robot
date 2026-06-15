from typing import Any

from nonebot import get_driver, on_message
from nonebot.adapters.onebot.v11 import (
    Bot,
    GroupMessageEvent,
    MessageEvent as OneBotMessageEvent,
    PrivateMessageEvent,
)

from kaka_protocol import NotificationRequest
from qq_adapter.actions import QQSendTextAction
from qq_adapter.config import get_settings
from qq_adapter.core_client import KakaCoreClient, KakaCoreClientError
from qq_adapter.pipeline import handle_onebot_text_event
from qq_adapter.sender import send_notification_request as _send_notification_request
from qq_adapter.trigger import should_handle_group_plaintext

matcher = on_message(priority=50, block=False)


@get_driver().on_startup
async def _startup_notice() -> None:
    """启动时输出一句提示，方便确认插件已经加载。"""

    settings = get_settings()
    print(f"qq-adapter 已加载，kaka-core 地址：{settings.core_base_url}")


@matcher.handle()
async def handle_kaka_message(bot: Bot, event: OneBotMessageEvent) -> None:
    """收到 QQ 文本消息后，把消息交给现有的 QQ 适配器流水线。"""

    handling = _classify_message_handling(bot, event)
    if handling is None:
        return

    raw_event = _event_to_onebot_raw_event(event, bot)
    core_client = KakaCoreClient(get_settings())

    try:
        actions = await handle_onebot_text_event(
            raw_event,
            core_client,
            should_reply=handling.should_reply,
            output_origin=handling.output_origin,
            output_reason=handling.output_reason,
        )
    except ValueError:
        # 当前阶段只处理文本消息，图片、语音、表情等后续再接。
        return
    except KakaCoreClientError:
        await bot.send(event, "卡咔核心服务暂时没连上。", at_sender=False)
        return

    for action in actions:
        await _send_text_action(bot, event, action)


def _should_handle_message(bot: Bot, event: OneBotMessageEvent) -> bool:
    """判断当前消息是否应该交给卡咔回复。

    第一阶段规则：
    - 私聊全部回复。
    - 群聊只有 @ 机器人或文本里包含“卡咔”时回复。
    """

    handling = _classify_message_handling(bot, event)
    return handling.should_reply if handling else False


class MessageHandling:
    """QQ 消息进入核心服务时的处理方式。"""

    def __init__(self, *, should_reply: bool, output_origin: str, output_reason: str) -> None:
        self.should_reply = should_reply
        self.output_origin = output_origin
        self.output_reason = output_reason


def _classify_message_handling(
    bot: Bot,
    event: OneBotMessageEvent,
) -> MessageHandling | None:
    """判断消息应该回复、只观察，还是忽略。"""

    if isinstance(event, PrivateMessageEvent):
        return MessageHandling(
            should_reply=True,
            output_origin="passive",
            output_reason="private",
        )

    if not isinstance(event, GroupMessageEvent):
        return None

    if should_handle_group_plaintext(event.get_plaintext()):
        return MessageHandling(
            should_reply=True,
            output_origin="passive",
            output_reason="keyword",
        )

    if _is_at_bot(bot, event):
        return MessageHandling(
            should_reply=True,
            output_origin="passive",
            output_reason="mention",
        )

    return MessageHandling(should_reply=False, output_origin="none", output_reason="none")


def _event_to_onebot_raw_event(
    event: OneBotMessageEvent,
    bot: Bot | None = None,
) -> dict[str, Any]:
    """把 NoneBot 的事件对象整理成现有处理流水线能处理的 OneBot 字典。"""

    raw = _model_to_dict(event)
    raw.setdefault("post_type", "message")
    raw["message"] = _extract_text_for_core(event, bot)

    if isinstance(event, GroupMessageEvent):
        raw["message_type"] = "group"
        raw["group_id"] = event.group_id
    elif isinstance(event, PrivateMessageEvent):
        raw["message_type"] = "private"
    else:
        raw.setdefault("message_type", getattr(event, "message_type", None))

    raw["user_id"] = event.user_id
    return raw


def _is_at_bot(bot: Bot, event: OneBotMessageEvent) -> bool:
    """判断消息是否 @ 了当前机器人。"""

    if event.is_tome():
        return True

    bot_id = str(bot.self_id)
    for segment in event.get_message():
        if segment.type != "at":
            continue
        if str(segment.data.get("qq")) == bot_id:
            return True

    raw_message = getattr(event, "raw_message", "") or ""
    if f"[CQ:at,qq={bot_id}]" in raw_message:
        return True
    if f"[at:qq={bot_id}]" in raw_message:
        return True

    return False


def _extract_text_for_core(
    event: OneBotMessageEvent,
    bot: Bot | None = None,
) -> str:
    """提取发给卡咔核心服务的纯文本。

    @ 消息经常由 at 段 + text 段组成。OneBot 文本流水线只处理文本，
    所以这里跳过 at 段，只保留真正的 text 内容。
    """

    text_parts: list[str] = []
    for segment in event.get_message():
        if segment.type != "text":
            continue
        text = segment.data.get("text")
        if isinstance(text, str):
            text_parts.append(text)

    text = "".join(text_parts).strip()
    if text:
        return text

    plaintext = event.get_plaintext().strip()
    if plaintext:
        return plaintext

    if bot is not None and _is_at_bot(bot, event):
        return "用户 @ 了卡咔。"

    if _has_at_segment(event):
        return "用户 @ 了其他人。"

    return ""


def _has_at_segment(event: OneBotMessageEvent) -> bool:
    """判断消息里是否包含 @ 段。"""

    for segment in event.get_message():
        if segment.type == "at":
            return True

    raw_message = getattr(event, "raw_message", "") or ""
    return "[CQ:at," in raw_message or "[at:qq=" in raw_message


def _model_to_dict(event: OneBotMessageEvent) -> dict[str, Any]:
    """兼容不同 Pydantic 版本的事件序列化方式。"""

    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    return event.dict()


async def _send_text_action(
    bot: Bot,
    event: OneBotMessageEvent,
    action: QQSendTextAction,
) -> None:
    """执行卡咔核心服务返回的文本发送动作。"""

    if isinstance(event, GroupMessageEvent):
        await bot.send_group_msg(group_id=int(action.scene_id), message=action.text)
        return

    if isinstance(event, PrivateMessageEvent):
        await bot.send_private_msg(user_id=int(action.scene_id), message=action.text)
        return

    await bot.send(event, action.text, at_sender=False)


async def send_notification_request(bot: Bot, request: NotificationRequest) -> None:
    """Send a proactive notification without relying on an inbound QQ event."""

    await _send_notification_request(bot, request)
