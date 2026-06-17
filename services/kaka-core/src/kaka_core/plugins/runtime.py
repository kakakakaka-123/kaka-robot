from dataclasses import dataclass
from functools import lru_cache

from kaka_core.plugins.builtin.desktop_operations import DesktopOperationsPlugin
from kaka_core.plugins.builtin.github_repo import GitHubRepositoryPlugin
from kaka_core.plugins.builtin.memory_search import MemorySearchPlugin
from kaka_core.plugins.builtin.n8n_webhook import N8nWebhookPlugin
from kaka_core.plugins.builtin.s60 import SixtySecondsPlugin
from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.registry import PluginRegistry
from kaka_core.plugins.result import PluginResult
from kaka_protocol import MessageEvent


DEFAULT_COMMAND_PREFIXES = ("/", "插件：", "插件:", "plugin:")


@dataclass(frozen=True)
class PluginCommand:
    plugin_id: str
    command_text: str


@dataclass(frozen=True)
class CommandShortcut:
    shortcut: str
    plugin_id: str
    command_text: str
    description: str


class PluginRuntime:
    """插件执行入口。"""

    def __init__(
        self,
        registry: PluginRegistry,
        *,
        enabled: bool,
        command_prefixes: tuple[str, ...] = DEFAULT_COMMAND_PREFIXES,
        shortcuts: tuple[CommandShortcut, ...] = (),
    ) -> None:
        self._registry = registry
        self._enabled = enabled
        self._command_prefixes = command_prefixes
        self._shortcuts: dict[str, CommandShortcut] = {}
        for s in shortcuts:
            self._shortcuts[s.shortcut.lower()] = s

    async def run_for_event(self, event: MessageEvent) -> PluginResult | None:
        if not self._enabled:
            return None

        command = self.parse_command(event.content.text or "")
        if command is None:
            return None

        # Handle built-in /help
        if command.plugin_id == "__builtin__" and command.command_text == "help":
            return self._build_help_result()

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
            body = stripped[len(prefix):].strip()
            if not body:
                return None

            # Built-in /help
            if body.lower() == "help":
                return PluginCommand(plugin_id="__builtin__", command_text="help")

            # Check shortcuts: the first token may be a registered shortcut
            first, _, rest = body.partition(" ")
            shortcut = self._shortcuts.get(first.lower())
            if shortcut:
                remainder = f" {rest}" if rest else ""
                return PluginCommand(
                    plugin_id=shortcut.plugin_id,
                    command_text=f"{shortcut.command_text}{remainder}",
                )

            # Normal parsing: plugin_id + optional arguments
            plugin_id, _, command_text = body.partition(" ")
            return PluginCommand(
                plugin_id=plugin_id.strip(),
                command_text=command_text.strip(),
            )
        return None

    def _build_help_result(self) -> PluginResult:
        lines = ["可用命令：", ""]

        # List shortcuts
        for _, s in sorted(self._shortcuts.items()):
            lines.append(f"/{s.shortcut}")
            lines.append(f"  {s.description}")
            lines.append("")

        # List registered plugins
        for plugin in self._registry.list_plugins():
            lines.append(f"{self._command_prefixes[0]}{plugin.id} ...")
            lines.append(f"  {plugin.description}")
            lines.append("")

        lines.append("/help")
        lines.append("  显示此帮助面板")

        return PluginResult.text_reply(
            "__builtin__",
            "\n".join(lines).rstrip(),
            metadata={"command": "help"},
        )


def create_default_plugin_runtime(
    *,
    enabled: bool,
    command_prefixes: tuple[str, ...] = DEFAULT_COMMAND_PREFIXES,
    n8n_webhook_base_url: str = "",
    n8n_webhook_timeout_seconds: float = 30.0,
    s60_base_url: str = "https://60s.viki.moe",
    s60_timeout_seconds: float = 15.0,
    github_api_base_url: str = "https://api.github.com",
    github_timeout_seconds: float = 15.0,
    github_token: str = "",
) -> PluginRuntime:
    # 运行时（含插件实例和它们持有的 httpx 连接池）按配置缓存，避免每条消息都
    # 重新构造注册表和插件、丢弃连接池。配置变化时缓存键自然失效并重建。
    return _build_cached_plugin_runtime(
        enabled,
        command_prefixes,
        n8n_webhook_base_url,
        n8n_webhook_timeout_seconds,
        s60_base_url,
        s60_timeout_seconds,
        github_api_base_url,
        github_timeout_seconds,
        github_token,
    )


@lru_cache(maxsize=8)
def _build_cached_plugin_runtime(
    enabled: bool,
    command_prefixes: tuple[str, ...],
    n8n_webhook_base_url: str,
    n8n_webhook_timeout_seconds: float,
    s60_base_url: str,
    s60_timeout_seconds: float,
    github_api_base_url: str,
    github_timeout_seconds: float,
    github_token: str,
) -> PluginRuntime:
    registry = PluginRegistry(
        [
            DesktopOperationsPlugin(),
            MemorySearchPlugin(),
            N8nWebhookPlugin(
                base_url=n8n_webhook_base_url,
                timeout_seconds=n8n_webhook_timeout_seconds,
            ),
            SixtySecondsPlugin(
                base_url=s60_base_url,
                timeout_seconds=s60_timeout_seconds,
            ),
            GitHubRepositoryPlugin(
                api_base_url=github_api_base_url,
                token=github_token,
                timeout_seconds=github_timeout_seconds,
            ),
        ]
    )
    return PluginRuntime(
        registry,
        enabled=enabled,
        command_prefixes=command_prefixes,
        shortcuts=(
            CommandShortcut(
                shortcut="github项目雷达",
                plugin_id="n8n",
                command_text="github_weekly_stars",
                description="查看本周 GitHub 项目雷达周报（成熟活跃、潜力、增长最快三榜）",
            ),
            CommandShortcut(
                shortcut="项目",
                plugin_id="github_repo",
                command_text="repo",
                description="查看 GitHub 项目基本信息，支持链接或 owner/repo",
            ),
            CommandShortcut(
                shortcut="项目搜索",
                plugin_id="github_repo",
                command_text="search",
                description="按关键词搜索 GitHub 项目",
            ),
            CommandShortcut(
                shortcut="今日新闻",
                plugin_id="60s",
                command_text="60s",
                description="查看今天的 60 秒新闻",
            ),
            CommandShortcut(
                shortcut="AI资讯",
                plugin_id="60s",
                command_text="ai-news",
                description="查看今天的 AI 资讯",
            ),
            CommandShortcut(
                shortcut="IT资讯",
                plugin_id="60s",
                command_text="it-news",
                description="查看今天的 IT 资讯",
            ),
        ),
    )
