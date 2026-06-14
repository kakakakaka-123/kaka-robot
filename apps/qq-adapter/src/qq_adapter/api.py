from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status

from kaka_protocol import ContentType, NotificationRequest, NotificationResult, Platform, SceneType
from qq_adapter.config import get_settings


def _require_send_token(authorization: str | None) -> None:
    token = get_settings().send_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QQ adapter send token is not configured",
        )
    if authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid QQ adapter send token",
        )


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


def create_send_api(get_bot: Callable[[], Any]) -> FastAPI:
    """Create a local API for proactive QQ notification delivery."""

    app = FastAPI(title="kaka QQ adapter send API")

    @app.post("/v1/send", response_model=NotificationResult)
    async def send(
        request: NotificationRequest,
        authorization: str | None = Header(default=None),
    ) -> NotificationResult:
        _require_send_token(authorization)
        if request.target.platform != Platform.QQ:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported platform: {request.target.platform}",
            )

        try:
            bot = get_bot()
            await send_notification_request(bot, request)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        return NotificationResult(
            accepted=True,
            delivered=True,
            target=request.target,
            metadata={"adapter": "qq", "source": request.source},
        )

    return app
