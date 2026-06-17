from typing import Any

import httpx

from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.result import PluginResult


MAX_REPLY_CHARS = 1800

ENDPOINTS = {
    "60s": ("60s", "今日 60 秒新闻"),
    "news": ("60s", "今日 60 秒新闻"),
    "today": ("60s", "今日 60 秒新闻"),
    "ai-news": ("ai-news", "今日 AI 资讯"),
    "ai": ("ai-news", "今日 AI 资讯"),
    "it-news": ("it-news", "今日 IT 资讯"),
    "it": ("it-news", "今日 IT 资讯"),
}


class SixtySecondsPlugin:
    id = "60s"
    name = "60s API"
    description = "查询每日 60 秒新闻、AI 资讯和 IT 资讯。"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
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
        return self._parse_endpoint(context.command_text)[0] is not None

    async def run(self, context: PluginContext) -> PluginResult:
        endpoint, title = self._parse_endpoint(context.command_text)
        if endpoint is None or title is None:
            return PluginResult.text_reply(
                self.id,
                "可以用 /今日新闻、/AI资讯 或 /IT资讯 叫卡咔查询。",
                metadata={"plugin_error": "unknown_60s_command"},
            )

        if not self._base_url:
            return PluginResult.text_reply(
                self.id,
                "还没有配置 60s API 地址。",
                metadata={"endpoint": endpoint, "plugin_error": "missing_60s_base_url"},
            )

        try:
            response = await self._get_client().get(
                f"{self._base_url}/v2/{endpoint}",
                params={"encoding": "markdown"},
            )
        except httpx.HTTPError as exc:
            return self._error_result(endpoint, "request_failed", str(exc))

        if response.status_code != 200:
            return self._error_result(
                endpoint,
                "unexpected_status",
                f"HTTP {response.status_code}",
                status_code=response.status_code,
            )

        text = self._extract_response_text(response, title)
        if not text:
            text = f"{title}\n\n今天暂时没有取到可展示的内容。"

        return PluginResult.text_reply(
            self.id,
            self._trim_reply(text),
            metadata={"endpoint": endpoint, "source": "60s-api"},
        )

    def _parse_endpoint(self, command_text: str) -> tuple[str | None, str | None]:
        command = command_text.strip().lower()
        first_token = command.split(maxsplit=1)[0] if command else "60s"
        return ENDPOINTS.get(first_token, (None, None))

    def _extract_response_text(self, response: httpx.Response, title: str) -> str:
        content_type = response.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            try:
                body = response.json()
            except ValueError:
                return response.text.strip()
            return self._json_to_text(body, title)
        return response.text.strip()

    def _json_to_text(self, body: Any, title: str) -> str:
        if not isinstance(body, dict):
            return ""

        data = body.get("data")
        if isinstance(data, str):
            return data.strip()

        if isinstance(data, dict):
            text = self._text_from_data_dict(data, title)
            if text:
                return text

        for key in ("text", "content", "message", "msg"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        return ""

    def _text_from_data_dict(self, data: dict[str, Any], title: str) -> str:
        for key in ("text", "content", "markdown"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        news = data.get("news")
        if isinstance(news, list):
            lines = [title, ""]
            for index, item in enumerate(news, start=1):
                text = self._format_item(index, item)
                if text:
                    lines.append(text)
            tip = data.get("tip") or data.get("sentence")
            if isinstance(tip, str) and tip.strip():
                lines.extend(["", tip.strip()])
            return "\n".join(lines).strip()

        items = data.get("items")
        if isinstance(items, list):
            lines = [title, ""]
            for index, item in enumerate(items, start=1):
                text = self._format_item(index, item)
                if text:
                    lines.append(text)
            return "\n".join(lines).strip()

        return ""

    def _format_item(self, index: int, item: Any) -> str:
        if isinstance(item, str):
            text = item.strip()
            return f"{index}. {text}" if text else ""
        if not isinstance(item, dict):
            return ""

        title = str(item.get("title") or item.get("name") or item.get("content") or "").strip()
        detail = str(
            item.get("detail")
            or item.get("description")
            or item.get("desc")
            or item.get("summary")
            or ""
        ).strip()
        source = str(item.get("source") or "").strip()
        url = str(item.get("url") or item.get("link") or "").strip()
        if not title and detail:
            title, detail = detail, ""
        if not title:
            return ""

        lines = [f"{index}. {title}"]
        if detail and detail != title:
            lines.append(f"   {detail}")
        if source:
            lines.append(f"   来源：{source}")
        if url:
            lines.append(f"   {url}")
        return "\n".join(lines)

    def _trim_reply(self, text: str) -> str:
        normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
        while "\n\n\n" in normalized:
            normalized = normalized.replace("\n\n\n", "\n\n")
        if len(normalized) <= MAX_REPLY_CHARS:
            return normalized
        return f"{normalized[:MAX_REPLY_CHARS].rstrip()}\n\n后面还有一些，卡咔先发这些。"

    def _error_result(
        self,
        endpoint: str,
        error: str,
        detail: str,
        *,
        status_code: int | None = None,
    ) -> PluginResult:
        metadata: dict[str, object] = {
            "endpoint": endpoint,
            "plugin_error": error,
            "error_detail": detail,
        }
        if status_code is not None:
            metadata["status_code"] = status_code
        return PluginResult.text_reply(
            self.id,
            "60s API 暂时没连上，卡咔晚点再看。",
            metadata=metadata,
        )
