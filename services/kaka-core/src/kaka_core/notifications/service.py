import httpx

from kaka_core.config.settings import NotificationSettings
from kaka_protocol import NotificationRequest, NotificationResult, Platform


class NotificationDeliveryError(RuntimeError):
    """Raised when a notification cannot be forwarded to its platform adapter."""


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
        raise NotificationDeliveryError("QQ adapter send base URL is not configured")

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
    except httpx.HTTPError as exc:
        raise NotificationDeliveryError(f"QQ adapter request failed: {exc}") from exc

    if response.status_code >= 400:
        raise NotificationDeliveryError(
            f"QQ adapter rejected notification: HTTP {response.status_code} {response.text}"
        )

    return NotificationResult.model_validate(response.json())
