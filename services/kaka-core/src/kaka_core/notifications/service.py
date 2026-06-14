import httpx
from pydantic import ValidationError

from kaka_core.config.settings import NotificationSettings
from kaka_protocol import NotificationRequest, NotificationResult, Platform


class NotificationDeliveryError(RuntimeError):
    """Raised when a notification cannot be forwarded to its platform adapter."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def deliver_notification(
    request: NotificationRequest,
    settings: NotificationSettings,
) -> NotificationResult:
    """Forward a normalized proactive notification to the target platform adapter."""

    if request.target.platform != Platform.QQ:
        raise NotificationDeliveryError(
            f"unsupported notification platform: {request.target.platform}"
        )
    if not settings.qq_adapter_send_base_url:
        raise NotificationDeliveryError(
            "QQ adapter send base URL is not configured",
            status_code=503,
        )

    url = f"{settings.qq_adapter_send_base_url}/v1/send"
    headers = {}
    if settings.qq_adapter_send_token:
        headers["Authorization"] = f"Bearer {settings.qq_adapter_send_token}"

    try:
        with httpx.Client(timeout=settings.adapter_timeout_seconds) as client:
            response = client.post(
                url,
                headers=headers,
                json=request.model_dump(mode="json", exclude_unset=True),
            )
    except httpx.TimeoutException as exc:
        raise NotificationDeliveryError(
            f"QQ adapter request timed out: {exc}",
            status_code=504,
        ) from exc
    except httpx.HTTPError as exc:
        raise NotificationDeliveryError(
            f"QQ adapter request failed: {exc}",
            status_code=503,
        ) from exc

    if response.status_code >= 400:
        raise NotificationDeliveryError(
            f"QQ adapter rejected notification: HTTP {response.status_code} {response.text}",
            status_code=502,
        )

    try:
        data = response.json()
        return NotificationResult.model_validate(data)
    except (ValueError, ValidationError) as exc:
        raise NotificationDeliveryError(
            f"invalid QQ adapter response: {exc}",
            status_code=502,
        ) from exc
