from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kaka_core.plugins import (
    KakaPlugin,
    MemorySearchPlugin,
    N8nWebhookPlugin,
    PluginContext,
    PluginRegistry,
    PluginResult,
    PluginRuntime,
    CommandShortcut,
)
from kaka_core.plugins.builtin.desktop_operations import DesktopOperationsPlugin
from kaka_core.plugins.builtin.github_repo import GitHubRepositoryPlugin
from kaka_core.plugins.builtin.s60 import SixtySecondsPlugin
from kaka_core.plugins.runtime import PluginCommand, create_default_plugin_runtime
from kaka_core.config.settings import get_settings
from kaka_core.storage.models import Base, MemoryRecord, SceneRecord, UserRecord
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def make_event(text: str = "插件：echo hello") -> MessageEvent:
    return MessageEvent(
        event_id="plugin-event-1",
        platform=Platform.QQ,
        scene_type=SceneType.GROUP,
        scene_id="20002",
        user_id="10001",
        display_name="测试用户",
        content=MessageContent.text_message(text),
        timestamp=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
        metadata={"source": "test"},
    )


class EchoPlugin:
    id = "echo"
    name = "回声"
    description = "测试插件。"

    async def can_handle(self, context: PluginContext) -> bool:
        return bool(context.command_text.strip())

    async def run(self, context: PluginContext) -> PluginResult:
        return PluginResult.text_reply(
            self.id,
            f"echo:{context.command_text}",
            metadata={"scene_id": context.scene_id},
        )


def test_plugin_context_is_platform_agnostic() -> None:
    context = PluginContext.from_event(make_event(), command_text="hello")

    assert context.event_id == "plugin-event-1"
    assert context.platform == "qq"
    assert context.scene_type == "group"
    assert context.scene_id == "20002"
    assert context.user_id == "10001"
    assert context.display_name == "测试用户"
    assert context.text == "插件：echo hello"
    assert context.command_text == "hello"
    assert context.metadata == {"source": "test"}


def test_plugin_registry_rejects_duplicate_ids() -> None:
    registry = PluginRegistry()
    registry.register(EchoPlugin())

    with pytest.raises(ValueError, match="echo"):
        registry.register(EchoPlugin())


def test_plugin_settings_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.setenv("PLUGIN_SYSTEM_ENABLED", "")
    get_settings.cache_clear()

    assert get_settings().plugins.enabled is False

    get_settings.cache_clear()


def test_plugin_settings_can_enable_runtime(monkeypatch) -> None:
    monkeypatch.setenv("PLUGIN_SYSTEM_ENABLED", "true")
    monkeypatch.setenv("PLUGIN_COMMAND_PREFIXES", "插件：,tool:")
    monkeypatch.setenv("PLUGIN_N8N_WEBHOOK_BASE_URL", "http://127.0.0.1:5678/webhook/kaka")
    monkeypatch.setenv("PLUGIN_N8N_WEBHOOK_TIMEOUT", "12.5")
    monkeypatch.setenv("PLUGIN_60S_BASE_URL", "https://60s.example.test")
    monkeypatch.setenv("PLUGIN_60S_TIMEOUT", "9.5")
    monkeypatch.setenv("PLUGIN_GITHUB_API_BASE_URL", "https://api.github.example.test")
    monkeypatch.setenv("PLUGIN_GITHUB_TIMEOUT", "7.5")
    monkeypatch.setenv("GITHUB_TOKEN", "github-token")
    get_settings.cache_clear()

    settings = get_settings().plugins

    assert settings.enabled is True
    assert settings.command_prefixes == ("插件：", "tool:")
    assert settings.n8n_webhook_base_url == "http://127.0.0.1:5678/webhook/kaka"
    assert settings.n8n_webhook_timeout_seconds == 12.5
    assert settings.s60_base_url == "https://60s.example.test"
    assert settings.s60_timeout_seconds == 9.5
    assert settings.github_api_base_url == "https://api.github.example.test"
    assert settings.github_timeout_seconds == 7.5
    assert settings.github_token == "github-token"

    get_settings.cache_clear()


def test_env_example_keeps_slash_plugin_command_prefix() -> None:
    lines = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    prefix_line = next(line for line in lines if line.startswith("PLUGIN_COMMAND_PREFIXES="))
    prefixes = [item.strip() for item in prefix_line.partition("=")[2].split(",") if item.strip()]

    assert "/" in prefixes


@pytest.mark.anyio
async def test_desktop_operations_owner_check_uses_relationship_settings(monkeypatch) -> None:
    monkeypatch.setenv("KAKA_OWNER_USER_IDS", "10001")
    get_settings.cache_clear()

    plugin = DesktopOperationsPlugin()
    monkeypatch.setattr(
        plugin,
        "_parse_command",
        lambda _: {
            "operation_type": "create_file",
            "params": {"filename": "owner.txt", "content": "ok"},
            "permission_level": 2,
        },
    )
    monkeypatch.setattr(plugin, "_create_operation", lambda _context, _command: 123)

    result = await plugin.run(PluginContext.from_event(make_event("/ignored"), command_text=""))

    assert result.plugin_id == "desktop_operations"
    assert result.text != "这个操作我不能做哦..."
    assert result.metadata["operation_id"] == 123

    get_settings.cache_clear()


@pytest.mark.anyio
async def test_disabled_plugin_runtime_does_not_handle_event() -> None:
    runtime = PluginRuntime(PluginRegistry([EchoPlugin()]), enabled=False)

    assert await runtime.run_for_event(make_event()) is None


@pytest.mark.anyio
async def test_plugin_runtime_invokes_explicit_command() -> None:
    runtime = PluginRuntime(PluginRegistry([EchoPlugin()]), enabled=True)

    result = await runtime.run_for_event(make_event("插件：echo hello kaka"))

    assert result is not None
    assert result.plugin_id == "echo"
    assert result.text == "echo:hello kaka"
    assert result.metadata["scene_id"] == "20002"


@pytest.mark.anyio
async def test_slash_prefix_routes_plugin() -> None:
    runtime = PluginRuntime(PluginRegistry([EchoPlugin()]), enabled=True)

    result = await runtime.run_for_event(make_event("/echo hi"))

    assert result is not None
    assert result.plugin_id == "echo"
    assert result.text == "echo:hi"


@pytest.mark.anyio
async def test_shortcut_routes_to_correct_plugin() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"text": "GitHub 项目雷达周报内容", "data": {"count": 5}},
        )

    n8n_plugin = N8nWebhookPlugin(
        base_url="http://n8n.local/webhook/kaka",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([n8n_plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="github项目雷达",
                plugin_id="n8n",
                command_text="github_weekly_stars",
                description="查看本周 GitHub 项目雷达周报",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/github项目雷达"))

    assert result is not None
    assert result.plugin_id == "n8n"
    assert result.text == "GitHub 项目雷达周报内容"
    assert captured["url"] == "http://n8n.local/webhook/kaka/github_weekly_stars"
    assert captured["payload"]["workflow"] == "github_weekly_stars"


@pytest.mark.anyio
async def test_shortcut_passes_extra_args() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"text": "ok"})

    n8n_plugin = N8nWebhookPlugin(
        base_url="http://n8n.local/webhook/kaka",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([n8n_plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="github项目雷达",
                plugin_id="n8n",
                command_text="github_weekly_stars",
                description="test",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/github项目雷达 python rust"))

    assert result is not None
    assert captured["payload"]["workflow"] == "github_weekly_stars"
    assert captured["payload"]["input"] == "python rust"


@pytest.mark.anyio
async def test_project_shortcut_routes_github_url_to_repo_lookup() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["token"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "full_name": "vikiboss/60s",
                "description": "开放 API 集合。",
                "html_url": "https://github.com/vikiboss/60s",
                "stargazers_count": 12345,
                "forks_count": 678,
                "open_issues_count": 9,
                "language": "TypeScript",
                "license": {"spdx_id": "MIT"},
                "default_branch": "main",
                "updated_at": "2026-06-16T01:02:03Z",
                "pushed_at": "2026-06-15T04:05:06Z",
                "archived": False,
                "fork": False,
            },
        )

    plugin = GitHubRepositoryPlugin(
        api_base_url="https://api.github.example.test",
        token="secret-token",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="项目",
                plugin_id="github_repo",
                command_text="repo",
                description="查看 GitHub 项目基本信息或搜索项目",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/项目 https://github.com/vikiboss/60s"))

    assert result is not None
    assert result.plugin_id == "github_repo"
    assert captured["path"] == "/repos/vikiboss/60s"
    assert captured["token"] == "Bearer secret-token"
    assert "GitHub 项目：vikiboss/60s" in result.text
    assert "开放 API 集合。" in result.text
    assert "Stars：12,345" in result.text
    assert "语言：TypeScript" in result.text
    assert "许可：MIT" in result.text
    assert "https://github.com/vikiboss/60s" in result.text
    assert result.metadata["mode"] == "repo"
    assert result.metadata["repo"] == "vikiboss/60s"


@pytest.mark.anyio
async def test_project_search_shortcut_queries_github_search() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["params"] = dict(request.url.params)
        return httpx.Response(
            200,
            json={
                "total_count": 2,
                "incomplete_results": False,
                "items": [
                    {
                        "full_name": "owner/agent-tool",
                        "description": "Agent tool project.",
                        "html_url": "https://github.com/owner/agent-tool",
                        "stargazers_count": 1000,
                        "forks_count": 50,
                        "open_issues_count": 3,
                        "language": "Python",
                        "updated_at": "2026-06-10T00:00:00Z",
                    },
                    {
                        "full_name": "team/agent-ui",
                        "description": "",
                        "html_url": "https://github.com/team/agent-ui",
                        "stargazers_count": 500,
                        "forks_count": 20,
                        "open_issues_count": 0,
                        "language": None,
                        "updated_at": "2026-06-09T00:00:00Z",
                    },
                ],
            },
        )

    plugin = GitHubRepositoryPlugin(
        api_base_url="https://api.github.example.test",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="项目搜索",
                plugin_id="github_repo",
                command_text="search",
                description="搜索 GitHub 项目",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/项目搜索 python agent"))

    assert result is not None
    assert result.plugin_id == "github_repo"
    assert captured["path"] == "/search/repositories"
    assert captured["params"] == {
        "q": "python agent",
        "sort": "stars",
        "order": "desc",
        "per_page": "5",
    }
    assert "GitHub 搜索：python agent" in result.text
    assert "找到约 2 个结果" in result.text
    assert "1. owner/agent-tool" in result.text
    assert "Stars：1,000" in result.text
    assert "Agent tool project." in result.text
    assert "2. team/agent-ui" in result.text
    assert "暂无简介" in result.text
    assert result.metadata["mode"] == "search"
    assert result.metadata["query"] == "python agent"


def test_default_runtime_includes_project_shortcuts() -> None:
    runtime = create_default_plugin_runtime(enabled=True)

    assert runtime.parse_command("/项目 vikiboss/60s") == PluginCommand(
        plugin_id="github_repo",
        command_text="repo vikiboss/60s",
    )
    assert runtime.parse_command("/项目搜索 python agent") == PluginCommand(
        plugin_id="github_repo",
        command_text="search python agent",
    )


@pytest.mark.anyio
async def test_news_shortcut_routes_to_60s_plugin() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            text="# 每天 60 秒读懂世界\n\n1. 今天的第一条新闻。",
        )

    plugin = SixtySecondsPlugin(
        base_url="https://60s.example.test",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="今日新闻",
                plugin_id="60s",
                command_text="60s",
                description="查看今天的 60 秒新闻",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/今日新闻"))

    assert result is not None
    assert result.plugin_id == "60s"
    assert "每天 60 秒读懂世界" in result.text
    assert "今天的第一条新闻" in result.text
    assert captured["url"] == "https://60s.example.test/v2/60s?encoding=markdown"
    assert result.metadata["endpoint"] == "60s"


@pytest.mark.anyio
async def test_ai_news_shortcut_routes_to_60s_ai_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            text="# AI 资讯\n\n1. 新模型发布。",
        )

    plugin = SixtySecondsPlugin(
        base_url="https://60s.example.test",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="AI资讯",
                plugin_id="60s",
                command_text="ai-news",
                description="查看今天的 AI 资讯",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/AI资讯"))

    assert result is not None
    assert result.plugin_id == "60s"
    assert "AI 资讯" in result.text
    assert "新模型发布" in result.text
    assert captured["url"] == "https://60s.example.test/v2/ai-news?encoding=markdown"
    assert result.metadata["endpoint"] == "ai-news"


@pytest.mark.anyio
async def test_it_news_shortcut_routes_to_60s_it_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(
            200,
            text="# IT 资讯\n\n1. 新硬件发布。",
        )

    plugin = SixtySecondsPlugin(
        base_url="https://60s.example.test",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(
        PluginRegistry([plugin]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="IT资讯",
                plugin_id="60s",
                command_text="it-news",
                description="查看今天的 IT 资讯",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/IT资讯"))

    assert result is not None
    assert result.plugin_id == "60s"
    assert "IT 资讯" in result.text
    assert "新硬件发布" in result.text
    assert captured["url"] == "https://60s.example.test/v2/it-news?encoding=markdown"
    assert result.metadata["endpoint"] == "it-news"


def test_default_runtime_keeps_only_news_ai_news_and_it_news_shortcuts() -> None:
    runtime = create_default_plugin_runtime(enabled=True)

    assert runtime.parse_command("/今日新闻") == PluginCommand(
        plugin_id="60s",
        command_text="60s",
    )
    assert runtime.parse_command("/AI资讯") == PluginCommand(
        plugin_id="60s",
        command_text="ai-news",
    )
    assert runtime.parse_command("/IT资讯") == PluginCommand(
        plugin_id="60s",
        command_text="it-news",
    )
    assert runtime.parse_command("/60秒") == PluginCommand(
        plugin_id="60秒",
        command_text="",
    )


@pytest.mark.anyio
async def test_60s_plugin_extracts_text_from_json_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "news": ["第一条", "第二条"],
                    "tip": "每天都要认真生活。",
                },
            },
        )

    plugin = SixtySecondsPlugin(
        base_url="https://60s.example.test",
        transport=httpx.MockTransport(handler),
    )
    context = PluginContext.from_event(make_event("/60s 60s"), command_text="60s")

    result = await plugin.run(context)

    assert result.plugin_id == "60s"
    assert "今日 60 秒新闻" in result.text
    assert "1. 第一条" in result.text
    assert "2. 第二条" in result.text
    assert "每天都要认真生活。" in result.text


@pytest.mark.anyio
async def test_60s_plugin_formats_ai_news_json_items() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "news": [
                        {
                            "title": "新模型发布",
                            "detail": "支持更长上下文。",
                            "source": "AI 工具集",
                            "link": "https://example.test/ai",
                        },
                    ],
                },
            },
        )

    plugin = SixtySecondsPlugin(
        base_url="https://60s.example.test",
        transport=httpx.MockTransport(handler),
    )
    context = PluginContext.from_event(make_event("/60s ai-news"), command_text="ai-news")

    result = await plugin.run(context)

    assert result.plugin_id == "60s"
    assert "今日 AI 资讯" in result.text
    assert "1. 新模型发布" in result.text
    assert "支持更长上下文。" in result.text
    assert "来源：AI 工具集" in result.text
    assert "https://example.test/ai" in result.text
    assert "{'title'" not in result.text


@pytest.mark.anyio
async def test_60s_plugin_reports_http_error_without_traceback() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="service unavailable")

    plugin = SixtySecondsPlugin(
        base_url="https://60s.example.test",
        transport=httpx.MockTransport(handler),
    )
    context = PluginContext.from_event(make_event("/60s 60s"), command_text="60s")

    result = await plugin.run(context)

    assert result.plugin_id == "60s"
    assert "60s API 暂时没连上" in result.text
    assert result.metadata["plugin_error"] == "unexpected_status"
    assert result.metadata["status_code"] == 503


@pytest.mark.anyio
async def test_help_command_lists_shortcuts_and_plugins() -> None:
    runtime = PluginRuntime(
        PluginRegistry([EchoPlugin()]),
        enabled=True,
        shortcuts=(
            CommandShortcut(
                shortcut="github项目雷达",
                plugin_id="n8n",
                command_text="github_weekly_stars",
                description="查看本周 GitHub 项目雷达周报",
            ),
        ),
    )

    result = await runtime.run_for_event(make_event("/help"))

    assert result is not None
    assert result.plugin_id == "__builtin__"
    assert "github项目雷达" in result.text
    assert "echo" in result.text
    assert "帮助面板" in result.text


@pytest.mark.anyio
async def test_old_command_format_still_works() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"text": "周报内容"})

    n8n_plugin = N8nWebhookPlugin(
        base_url="http://n8n.local/webhook/kaka",
        transport=httpx.MockTransport(handler),
    )
    runtime = PluginRuntime(PluginRegistry([n8n_plugin]), enabled=True)

    result = await runtime.run_for_event(make_event("插件：n8n github_weekly_stars"))

    assert result is not None
    assert result.plugin_id == "n8n"
    assert captured["url"] == "http://n8n.local/webhook/kaka/github_weekly_stars"


@pytest.mark.anyio
async def test_parse_command_no_match_returns_none() -> None:
    runtime = PluginRuntime(PluginRegistry([EchoPlugin()]), enabled=True)

    assert runtime.parse_command("hello world") is None
    assert runtime.parse_command("") is None


def test_shortcut_immutability() -> None:
    """Shortcuts are frozen dataclasses and hashable."""
    s1 = CommandShortcut(
        shortcut="test",
        plugin_id="n8n",
        command_text="wf",
        description="d",
    )
    s2 = CommandShortcut(
        shortcut="test",
        plugin_id="n8n",
        command_text="wf",
        description="d",
    )
    assert s1 == s2
    assert hash(s1) == hash(s2)


@pytest.mark.anyio
async def test_memory_search_plugin_uses_normalized_context_without_platform_adapter() -> None:
    session_factory = create_memory_session_factory()
    with session_factory() as session:
        user = seed_user(session, "10001")
        scene = seed_scene(session, "group", "20002")
        seed_memory(session, user, scene, "用户正在研究卡咔插件系统。")
        seed_memory(session, user, scene, "用户喜欢直接、务实的回答。")
        session.commit()

    plugin = MemorySearchPlugin(session_factory=session_factory)
    context = PluginContext.from_event(
        make_event("插件：memory_search 插件系统"),
        command_text="插件系统",
    )

    result = await plugin.run(context)

    assert result.plugin_id == "memory_search"
    assert "用户正在研究卡咔插件系统。" in result.text
    assert result.metadata["memory_count"] >= 1


@pytest.mark.anyio
async def test_n8n_webhook_plugin_posts_normalized_payload_and_returns_text() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "text": "今天有 3 个值得看的项目。",
                "data": {"count": 3},
                "metadata": {"source": "n8n-test"},
            },
        )

    plugin = N8nWebhookPlugin(
        base_url="http://n8n.local/webhook/kaka",
        transport=httpx.MockTransport(handler),
    )
    context = PluginContext.from_event(
        make_event("插件：n8n github_trending ai agent"),
        command_text="github_trending ai agent",
    )

    result = await plugin.run(context)

    assert captured["url"] == "http://n8n.local/webhook/kaka/github_trending"
    assert captured["payload"] == {
        "workflow": "github_trending",
        "input": "ai agent",
        "event_id": "plugin-event-1",
        "platform": "qq",
        "scene_type": "group",
        "scene_id": "20002",
        "user_id": "10001",
        "display_name": "测试用户",
        "text": "插件：n8n github_trending ai agent",
        "metadata": {"source": "test"},
    }
    assert result.plugin_id == "n8n"
    assert result.text == "今天有 3 个值得看的项目。"
    assert result.data == {"count": 3}
    assert result.metadata["workflow"] == "github_trending"
    assert result.metadata["source"] == "n8n-test"


@pytest.mark.anyio
async def test_n8n_webhook_plugin_reports_missing_base_url() -> None:
    plugin = N8nWebhookPlugin(base_url="")
    context = PluginContext.from_event(
        make_event("插件：n8n github_trending ai agent"),
        command_text="github_trending ai agent",
    )

    result = await plugin.run(context)

    assert result.plugin_id == "n8n"
    assert "还没有配置 n8n webhook 地址" in result.text
    assert result.metadata["plugin_error"] == "missing_n8n_webhook_base_url"


def create_memory_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_user(session, platform_user_id: str) -> UserRecord:
    user = UserRecord(
        platform="qq",
        platform_user_id=platform_user_id,
        display_name=f"用户{platform_user_id}",
        created_at=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
    )
    session.add(user)
    session.flush()
    return user


def seed_scene(session, scene_type: str, scene_id: str) -> SceneRecord:
    scene = SceneRecord(
        platform="qq",
        scene_type=scene_type,
        scene_id=scene_id,
        created_at=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
    )
    session.add(scene)
    session.flush()
    return scene


def seed_memory(
    session,
    user: UserRecord,
    scene: SceneRecord,
    memory_text: str,
) -> MemoryRecord:
    memory = MemoryRecord(
        user_id=user.id,
        scene_id=scene.id,
        memory_text=memory_text,
        normalized_text=memory_text.rstrip("。"),
        memory_type="user_fact",
        confidence=0.9,
        source_text=memory_text,
        source="candidate",
        status="active",
        merge_reason="测试记忆",
        created_at=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 10, 8, 0, tzinfo=timezone.utc),
    )
    session.add(memory)
    session.flush()
    return memory
