from collections.abc import Callable

from sqlalchemy.orm import Session

from kaka_core.memory.search import MemorySearchFilters, search_user_memories
from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.result import PluginResult
from kaka_core.storage.database import create_session_factory, init_database


class MemorySearchPlugin:
    id = "memory_search"
    name = "记忆查询"
    description = "查询当前用户的长期记忆。"

    def __init__(self, session_factory: Callable[[], Session] | None = None) -> None:
        self._session_factory = session_factory

    async def can_handle(self, context: PluginContext) -> bool:
        return bool(context.command_text.strip())

    async def run(self, context: PluginContext) -> PluginResult:
        query_text = context.command_text.strip()
        if not query_text:
            return PluginResult.text_reply(self.id, "要查什么记忆，得先给卡咔一个关键词。")

        session_factory = self._session_factory
        if session_factory is None:
            init_database()
            session_factory = create_session_factory()

        with session_factory() as session:
            results = search_user_memories(
                session,
                MemorySearchFilters(
                    platform=context.platform,
                    user_id=context.user_id,
                    query_text=query_text,
                    limit=5,
                    target_scene_type=context.scene_type,
                    target_scene_id=context.scene_id,
                ),
            )

        if not results:
            return PluginResult.text_reply(
                self.id,
                "卡咔这里没有找到相关长期记忆。",
                metadata={"memory_count": 0, "used_memory_ids": []},
            )

        lines = ["卡咔找到这些相关记忆："]
        for index, result in enumerate(results, start=1):
            lines.append(f"{index}. {result.memory.memory_text}")
        return PluginResult.text_reply(
            self.id,
            "\n".join(lines),
            metadata={
                "memory_count": len(results),
                "used_memory_ids": [result.memory.id for result in results],
            },
        )
