"""统一推送服务 - 多平台适配层。

支持平台：
- QQ (已实现)
- 未来: Desktop, WeChat, Telegram, Web
"""

import time
from abc import ABC, abstractmethod
from threading import Lock

import httpx
from pydantic import ValidationError

from kaka_core.config.settings import NotificationSettings
from kaka_protocol import NotificationRequest, NotificationResult, Platform


# 幂等去重配置
_IDEMPOTENCY_TTL_SECONDS = 3600
_idempotency_lock = Lock()
_delivered_keys: dict[str, float] = {}


class NotificationDeliveryError(RuntimeError):
    """推送失败异常。"""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class PlatformAdapter(ABC):
    """平台推送适配器抽象基类。"""

    @abstractmethod
    async def deliver(
        self,
        request: NotificationRequest,
        settings: NotificationSettings,
    ) -> NotificationResult:
        """投递通知到目标平台。"""
        pass

    @abstractmethod
    def is_available(self, settings: NotificationSettings) -> bool:
        """检查该平台是否已配置可用。"""
        pass


class QQAdapter(PlatformAdapter):
    """QQ 平台适配器。"""

    async def deliver(
        self,
        request: NotificationRequest,
        settings: NotificationSettings,
    ) -> NotificationResult:
        """投递到 QQ 适配器。"""
        url = f"{settings.qq_adapter_send_base_url}/v1/send"
        headers = {}
        if settings.qq_adapter_send_token:
            headers["Authorization"] = f"Bearer {settings.qq_adapter_send_token}"

        try:
            async with httpx.AsyncClient(timeout=settings.adapter_timeout_seconds) as client:
                response = await client.post(
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

    def is_available(self, settings: NotificationSettings) -> bool:
        """检查 QQ 适配器是否已配置。"""
        return bool(settings.qq_adapter_send_base_url)


class UnifiedNotificationService:
    """统一推送服务。

    负责：
    - 平台路由
    - 幂等去重
    - 失败重试
    - 推送队列（可选）
    """

    def __init__(self):
        self._adapters: dict[Platform, PlatformAdapter] = {
            Platform.QQ: QQAdapter(),
        }

    async def deliver(
        self,
        request: NotificationRequest,
        settings: NotificationSettings,
    ) -> NotificationResult:
        """统一推送入口。"""
        # 1. 幂等去重
        if request.idempotency_key:
            if self._is_duplicate(request.idempotency_key):
                return NotificationResult(
                    accepted=True,
                    delivered=True,
                    target=request.target,
                    metadata={
                        "deduplicated": True,
                        "idempotency_key": request.idempotency_key,
                    },
                )
            self._mark_delivered(request.idempotency_key)

        # 2. 获取平台适配器
        adapter = self._adapters.get(request.target.platform)
        if not adapter:
            raise NotificationDeliveryError(
                f"unsupported notification platform: {request.target.platform}"
            )

        # 3. 检查平台是否可用
        if not adapter.is_available(settings):
            raise NotificationDeliveryError(
                f"{request.target.platform.value} adapter is not configured",
                status_code=503,
            )

        # 4. 投递
        return await adapter.deliver(request, settings)

    def _is_duplicate(self, key: str) -> bool:
        """检查是否重复推送。"""
        now = time.monotonic()
        with _idempotency_lock:
            # 清理过期条目
            expired = [k for k, exp in _delivered_keys.items() if exp <= now]
            for k in expired:
                _delivered_keys.pop(k, None)

            return key in _delivered_keys

    def _mark_delivered(self, key: str) -> None:
        """标记已推送。"""
        now = time.monotonic()
        with _idempotency_lock:
            _delivered_keys[key] = now + _IDEMPOTENCY_TTL_SECONDS


# 全局单例
_service = UnifiedNotificationService()


async def deliver_notification(
    request: NotificationRequest,
    settings: NotificationSettings,
) -> NotificationResult:
    """统一推送入口（向后兼容旧接口）。"""
    return await _service.deliver(request, settings)
