from dataclasses import dataclass

from kaka_core.plugins.builtin.memory_search import MemorySearchPlugin
from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.registry import PluginRegistry
from kaka_core.plugins.result import PluginResult
from kaka_protocol import MessageEvent


DEFAULT_COMMAND_PREFIXES = ("插件：", "插件:", "plugin:")


@dataclass(frozen=True)
class PluginCommand:
    plugin_id: str
    command_text: str


class PluginRuntime:
    """插件执行入口。"""

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        enabled: bool,
        command_prefixes: tuple[str, ...] = DEFAULT_COMMAND_PREFIXES,
    ) -> None:
        self._registry = registry
        self._enabled = enabled
        self._command_prefixes = command_prefixes

    async def run_for_event(self, event: MessageEvent) -> PluginResult | None:
        if not self._enabled:
            return None

        command = self.parse_command(event.content.text or "")
        if command is None:
            return None

        plugin = self._registry.get(command.plugin_id)
        if plugin is None:
            return PluginResult.text_reply(
                command.plugin_id,
                f"没有找到插件：{command.plugin_id}",
                metadata={"plugin_error": "not_found"},
            )

        context = PluginContext.from_event(event, command_text=command.command_text)
        try:
            if not await plugin.can_handle(context):
                return None
            return await plugin.run(context)
        except Exception as exc:  # noqa: BLE001
            return PluginResult.text_reply(
                plugin.id,
                f"插件 {plugin.id} 执行失败：{exc}",
                metadata={"plugin_error": str(exc)},
            )

    def parse_command(self, text: str) -> PluginCommand | None:
        stripped = text.strip()
        for prefix in self._command_prefixes:
            if not stripped.lower().startswith(prefix.lower()):
                continue
            body = stripped[len(prefix) :].strip()
            if not body:
                return None
            plugin_id, _, command_text = body.partition(" ")
            return PluginCommand(plugin_id=plugin_id.strip(), command_text=command_text.strip())
        return None


def create_default_plugin_runtime(
    *,
    enabled: bool,
    command_prefixes: tuple[str, ...] = DEFAULT_COMMAND_PREFIXES,
) -> PluginRuntime:
    registry = PluginRegistry([MemorySearchPlugin()])
    return PluginRuntime(
        registry,
        enabled=enabled,
        command_prefixes=command_prefixes,
    )
