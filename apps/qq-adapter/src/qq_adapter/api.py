from collections.abc import Callable
from json import JSONDecodeError
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import ValidationError

from kaka_protocol import NotificationRequest, NotificationResult, Platform
from qq_adapter.config import get_settings
from qq_adapter.sender import send_notification_request


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


def create_send_api(get_bot: Callable[[], Any]) -> FastAPI:
    """Create a local API for proactive QQ notification delivery."""

    app = FastAPI(title="kaka QQ adapter send API")

    @app.post("/v1/send", response_model=NotificationResult)
    async def send(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> NotificationResult:
        _require_send_token(authorization)
        try:
            payload = await request.json()
            notification = NotificationRequest.model_validate(payload)
        except (JSONDecodeError, ValidationError) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="invalid notification request",
            ) from exc

        if notification.target.platform != Platform.QQ:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unsupported platform: {notification.target.platform}",
            )

        try:
            bot = get_bot()
            await send_notification_request(bot, notification)
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
            target=notification.target,
            metadata={"adapter": "qq", "source": notification.source},
        )

    return app
