from dataclasses import dataclass
from typing import Literal

import httpx

from kaka_core.config.settings import LLMSettings

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True)
class ChatMessage:
    """发送给大模型的一条聊天消息。"""

    role: ChatRole
    content: str


class LLMClientError(RuntimeError):
    """大模型调用失败时抛出的错误。"""


class LLMClient:
    """兼容通用聊天补全接口风格的大模型客户端。

    DeepSeek API 兼容这种聊天补全接口。
    这里不把代码写死到 DeepSeek，后续其他兼容服务也可以复用。
    """

    def __init__(self, settings: LLMSettings) -> None:
        self._settings = settings

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        """调用聊天模型并返回文本结果。"""

        if not self._settings.can_call_remote:
            raise LLMClientError("LLM 未启用或缺少 LLM_API_KEY。")

        payload = {
            "model": model or self._settings.chat_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "temperature": self._settings.temperature,
            "max_tokens": self._settings.max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self._settings.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._settings.base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=self._settings.request_timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code >= 400:
            raise LLMClientError(
                f"LLM 请求失败：HTTP {response.status_code} {response.text}"
            )

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMClientError(f"LLM 返回格式异常：{data}") from exc

        if not isinstance(content, str) or not content.strip():
            raise LLMClientError("LLM 返回了空内容。")

        return content.strip()
