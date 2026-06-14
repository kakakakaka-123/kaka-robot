from fastapi import APIRouter, Header, HTTPException, status

from kaka_core.chat.service import generate_chat_response, observe_message
from kaka_core.config.settings import get_settings
from kaka_core.notifications import NotificationDeliveryError, deliver_notification
from kaka_protocol import KakaResponse, MessageEvent, NotificationRequest, NotificationResult

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    """健康检查接口。

    后续部署、测试和适配器都可以用它判断 kaka-core 是否启动。
    """

    return {"status": "ok", "service": "kaka-core"}


def _require_notification_token(authorization: str | None) -> None:
    settings = get_settings()
    token = settings.notifications.token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="notification token is not configured",
        )
    if authorization != f"Bearer {token}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid notification token",
        )


@router.post("/v1/chat", response_model=KakaResponse)
async def chat(event: MessageEvent) -> KakaResponse:
    """接收统一消息事件，并返回统一响应。

    当前会在配置允许时调用 LLM。
    如果没有配置 API Key，则返回本地占位回复，保证开发测试不被阻塞。
    """

    return await generate_chat_response(event)


@router.post("/v1/observe", response_model=KakaResponse)
async def observe(event: MessageEvent) -> KakaResponse:
    """接收只观察不回复的统一消息事件。"""

    return observe_message(event)


@router.post("/v1/notifications", response_model=NotificationResult)
def notify(
    request: NotificationRequest,
    authorization: str | None = Header(default=None),
) -> NotificationResult:
    """Receive a proactive external notification and forward it to the adapter."""

    _require_notification_token(authorization)
    settings = get_settings()
    try:
        return deliver_notification(request, settings.notifications)
    except NotificationDeliveryError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
