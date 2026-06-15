from typing import Any

from kaka_protocol import ContentType, NotificationRequest, SceneType


async def send_notification_request(bot: Any, request: NotificationRequest) -> None:
    """Send a proactive notification without relying on an inbound QQ event."""

    text = request.content.text
    if request.content.type != ContentType.TEXT or not text:
        raise ValueError("only non-empty text notifications are supported")

    if request.target.scene_type == SceneType.GROUP:
        await bot.send_group_msg(group_id=int(request.target.scene_id), message=text)
        return

    if request.target.scene_type == SceneType.PRIVATE:
        await bot.send_private_msg(user_id=int(request.target.scene_id), message=text)
        return

    raise ValueError(f"unsupported QQ notification scene type: {request.target.scene_type}")
