from typing import Any
from urllib.parse import quote

import httpx

from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.result import PluginResult


class N8nWebhookPlugin:
    id = "n8n"
    name = "n8n 工作流"
    description = "调用外部 n8n webhook 工作流。"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        # 复用一个持久的 AsyncClient 以共享连接池；插件实例随运行时缓存存活，
        # 不再每次调用都新建并丢弃客户端（每次都要重新建立 TCP/TLS 连接）。
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def can_handle(self, context: PluginContext) -> bool:
        workflow, _ = self._parse_command(context.command_text)
        return bool(workflow)

    async def run(self, context: PluginContext) -> PluginResult:
        workflow, workflow_input = self._parse_command(context.command_text)
        if not workflow:
            return PluginResult.text_reply(self.id, "要调用哪个 n8n 工作流，得先告诉卡咔。")

        if not self._base_url:
            return PluginResult.text_reply(
                self.id,
                "还没有配置 n8n webhook 地址。",
                metadata={
                    "workflow": workflow,
                    "plugin_error": "missing_n8n_webhook_base_url",
                },
            )

        payload = self._build_payload(context, workflow, workflow_input)
        try:
            client = self._get_client()
            response = await client.post(self._workflow_url(workflow), json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            return PluginResult.text_reply(
                self.id,
                f"n8n 工作流 {workflow} 调用失败：{exc}",
                metadata={"workflow": workflow, "plugin_error": str(exc)},
            )

        return self._response_to_result(workflow, response)

    def _workflow_url(self, workflow: str) -> str:
        return f"{self._base_url}/{quote(workflow, safe='')}"

    def _build_payload(
        self,
        context: PluginContext,
        workflow: str,
        workflow_input: str,
    ) -> dict[str, Any]:
        return {
            "workflow": workflow,
            "input": workflow_input,
            "event_id": context.event_id,
            "platform": context.platform,
            "scene_type": context.scene_type,
            "scene_id": context.scene_id,
            "user_id": context.user_id,
            "display_name": context.display_name,
            "text": context.text,
            "metadata": context.metadata,
        }

    def _response_to_result(self, workflow: str, response: httpx.Response) -> PluginResult:
        try:
            body = response.json()
        except ValueError:
            return PluginResult.text_reply(
                self.id,
                response.text.strip() or "n8n 工作流已执行，但没有返回文本。",
                metadata={"workflow": workflow},
            )

        if not isinstance(body, dict):
            return PluginResult.text_reply(
                self.id,
                "n8n 工作流已执行，但返回格式不是对象。",
                metadata={"workflow": workflow, "plugin_error": "invalid_n8n_response"},
            )

        text = str(
            body.get("text") or body.get("reply") or body.get("message") or ""
        ).strip()
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        merged_metadata = {"workflow": workflow, **metadata}
        return PluginResult(
            plugin_id=self.id,
            text=text or "n8n 工作流已执行，但没有返回文本。",
            data=data,
            metadata=merged_metadata,
        )

    def _parse_command(self, command_text: str) -> tuple[str, str]:
        workflow, _, workflow_input = command_text.strip().partition(" ")
        return workflow.strip(), workflow_input.strip()
