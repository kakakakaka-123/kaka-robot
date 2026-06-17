from typing import Any

from nonebot.adapters.onebot.v11 import MessageSegment

from kaka_protocol import ContentType, NotificationRequest, SceneType


async def send_notification_request(bot: Any, request: NotificationRequest) -> None:
    """Send a proactive notification without relying on an inbound QQ event."""

    text = request.content.text
    if request.content.type != ContentType.TEXT or not text:
        raise ValueError("only non-empty text notifications are supported")

    try:
        scene_id = int(request.target.scene_id)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"invalid QQ notification scene id: {request.target.scene_id!r}"
        ) from exc

    # 用 MessageSegment.text 包裹纯文本，避免 OneBot V11 把通知里的
    # [CQ:at,qq=all] / [CQ:image,...] 等内容当成 CQ 码执行。
    text_segment = MessageSegment.text(text)

    if request.target.scene_type == SceneType.GROUP:
        await bot.send_group_msg(group_id=scene_id, message=text_segment)
        return

    if request.target.scene_type == SceneType.PRIVATE:
        await bot.send_private_msg(user_id=scene_id, message=text_segment)
        return

    raise ValueError(f"unsupported QQ notification scene type: {request.target.scene_type}")
