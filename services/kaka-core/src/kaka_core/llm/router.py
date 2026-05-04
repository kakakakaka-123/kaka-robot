from kaka_core.config.settings import LLMSettings
from kaka_core.llm.client import ChatMessage, LLMClient


class LLMRouter:
    """模型路由器。

    第一版只真正使用普通聊天模型。
    后续可以在这里按任务类型分流到推理模型、记忆模型、工具决策模型或多模态模型。
    """

    def __init__(self, settings: LLMSettings, client: LLMClient | None = None) -> None:
        self._settings = settings
        self._client = client or LLMClient(settings)

    async def chat(self, messages: list[ChatMessage]) -> str:
        """普通聊天任务。"""

        return await self._client.chat(messages, model=self._settings.chat_model)

    async def reason(self, messages: list[ChatMessage]) -> str:
        """复杂推理任务的预留入口。"""

        return await self._client.chat(messages, model=self._settings.reasoning_model)

    async def summarize_memory(self, messages: list[ChatMessage]) -> str:
        """记忆整理任务的预留入口。"""

        return await self._client.chat(messages, model=self._settings.memory_model)

    async def decide_tool(self, messages: list[ChatMessage]) -> str:
        """工具决策任务的预留入口。"""

        return await self._client.chat(messages, model=self._settings.tool_model)
