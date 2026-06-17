import httpx

from kaka_protocol import KakaResponse, MessageEvent

from qq_adapter.config import QQAdapterSettings


class KakaCoreClientError(RuntimeError):
    """调用卡咔核心服务失败时抛出的错误。"""


class KakaCoreClient:
    """卡咔核心服务的 HTTP 客户端。

    QQ 适配器不直接调用大模型，也不处理人格和记忆。
    它只把统一消息事件交给卡咔核心服务，再拿回统一响应。
    """

    def __init__(self, settings: QQAdapterSettings) -> None:
        self._settings = settings

    async def chat(self, event: MessageEvent) -> KakaResponse:
        """把统一消息事件发送给卡咔核心服务的 /v1/chat。"""

        return await self._post_event("/v1/chat", event)

    async def observe(self, event: MessageEvent) -> KakaResponse:
        """把统一消息事件发送给卡咔核心服务的 /v1/observe。"""

        return await self._post_event("/v1/observe", event)

    async def _post_event(self, path: str, event: MessageEvent) -> KakaResponse:
        """发送统一消息事件，并把结果解析成统一响应。"""

        url = f"{self._settings.core_base_url}{path}"

        try:
            async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
                response = await client.post(url, json=event.model_dump(mode="json"))
        except httpx.HTTPError as exc:
            raise KakaCoreClientError(f"kaka-core 连接失败：{exc}") from exc

        if response.status_code >= 400:
            raise KakaCoreClientError(
                f"kaka-core 请求失败：HTTP {response.status_code} {response.text[:200]}"
            )

        return KakaResponse.model_validate(response.json())
