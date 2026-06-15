from collections.abc import Iterable

from kaka_core.plugins.base import KakaPlugin


class PluginRegistry:
    """插件注册表。"""

    def __init__(self, plugins: Iterable[KakaPlugin] = ()) -> None:
        self._plugins: dict[str, KakaPlugin] = {}
        for plugin in plugins:
            self.register(plugin)

    def register(self, plugin: KakaPlugin) -> None:
        plugin_id = plugin.id.strip()
        if not plugin_id:
            raise ValueError("plugin id must not be empty")
        if plugin_id in self._plugins:
            raise ValueError(f"plugin already registered: {plugin_id}")
        self._plugins[plugin_id] = plugin

    def get(self, plugin_id: str) -> KakaPlugin | None:
        return self._plugins.get(plugin_id.strip())

    def list_plugins(self) -> tuple[KakaPlugin, ...]:
        return tuple(self._plugins.values())
