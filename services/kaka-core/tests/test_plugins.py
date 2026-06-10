from datetime import datetime, timezone
import json

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
)
from kaka_core.config.settings import get_settings
from kaka_core.storage.models import Base, MemoryRecord, SceneRecord, UserRecord
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType


def make_event(text: str = "插件：echo hello") -> MessageEvent:
    return MessageEvent(
        event_id="plugin-event-1",
        platform=Platform.QQ,
        scene_type=SceneType.GROUP,
        scene_id="20002",
        user_id="10001",
        display_name="无妄生欢",
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
    assert context.display_name == "无妄生欢"
    assert context.text == "插件：echo hello"
    assert context.command_text == "hello"
    assert context.metadata == {"source": "test"}


def test_plugin_registry_rejects_duplicate_ids() -> None:
    registry = PluginRegistry()
    registry.register(EchoPlugin())

    with pytest.raises(ValueError, match="echo"):
        registry.register(EchoPlugin())


def test_plugin_settings_are_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PLUGIN_SYSTEM_ENABLED", raising=False)
    get_settings.cache_clear()

    assert get_settings().plugins.enabled is False

    get_settings.cache_clear()


def test_plugin_settings_can_enable_runtime(monkeypatch) -> None:
    monkeypatch.setenv("PLUGIN_SYSTEM_ENABLED", "true")
    monkeypatch.setenv("PLUGIN_COMMAND_PREFIXES", "插件：,tool:")
    monkeypatch.setenv("PLUGIN_N8N_WEBHOOK_BASE_URL", "http://127.0.0.1:5678/webhook/kaka")
    monkeypatch.setenv("PLUGIN_N8N_WEBHOOK_TIMEOUT", "12.5")
    get_settings.cache_clear()

    settings = get_settings().plugins

    assert settings.enabled is True
    assert settings.command_prefixes == ("插件：", "tool:")
    assert settings.n8n_webhook_base_url == "http://127.0.0.1:5678/webhook/kaka"
    assert settings.n8n_webhook_timeout_seconds == 12.5

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
        "display_name": "无妄生欢",
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
