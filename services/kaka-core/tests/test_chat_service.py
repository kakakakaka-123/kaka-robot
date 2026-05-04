import asyncio

import pytest

from kaka_core.chat.service import generate_chat_response, observe_message
from kaka_core.config.settings import get_settings
from kaka_core.llm.client import ChatMessage
from kaka_core.storage.database import create_database_engine, init_database
from kaka_core.storage.models import (
    InputRecord,
    MemoryRecord,
    OutputRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker


class FakeRouter:
    """测试用模型路由器，不访问真实网络。"""

    def __init__(self) -> None:
        self.messages: list[ChatMessage] = []
        self.calls = 0

    async def chat(self, messages: list[ChatMessage]) -> str:
        self.calls += 1
        self.messages = messages
        assert messages[0].role == "system"
        assert "卡咔" in messages[0].content
        assert "用户消息：你好" in messages[1].content
        return "我在，刚刚听见了。"


class SlowFakeRouter(FakeRouter):
    async def chat(self, messages: list[ChatMessage]) -> str:
        await asyncio.sleep(0.05)
        return await super().chat(messages)


class BypassLockState:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()


def make_event() -> MessageEvent:
    return MessageEvent(
        platform=Platform.QQ,
        scene_type=SceneType.PRIVATE,
        scene_id="10001",
        user_id="10001",
        display_name="主人",
        content=MessageContent.text_message("你好"),
    )


@pytest.mark.anyio
async def test_generate_chat_response_uses_router_when_llm_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'router-test.sqlite3'}")
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_settings.cache_clear()

    response = await generate_chat_response(make_event(), router=FakeRouter())

    assert response.should_reply is True
    assert response.actions[0].content is not None
    assert response.actions[0].content.text == "我在，刚刚听见了。"
    assert response.metadata["llm_model"] == "deepseek-v4-flash"
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_generate_chat_response_injects_relevant_memories(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'memory-injection-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_REPLY_INJECTION_ENABLED", "true")
    monkeypatch.setenv("MEMORY_REPLY_LIMIT", "5")
    monkeypatch.setenv("MEMORY_REPLY_MIN_SCORE", "1.0")
    get_settings.cache_clear()
    seed_memory_database(database_url)

    router = FakeRouter()
    response = await generate_chat_response(make_event(), router=router)

    assert "可参考的长期记忆" in router.messages[0].content
    assert "均描述当前说话用户：主人，不是卡咔自己" in router.messages[0].content
    assert "当前说话用户：我喜欢回复先给结论。" in router.messages[0].content
    assert "不要把当前说话用户的身份、经历、偏好说成卡咔自己的身份、经历、偏好" in router.messages[0].content
    assert response.metadata["memory_injection_enabled"] is True
    assert response.metadata["memory_count"] == 1
    assert response.metadata["used_memory_ids"] == [1]
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_generate_chat_response_can_disable_memory_injection(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'memory-disabled-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("MEMORY_REPLY_INJECTION_ENABLED", "false")
    get_settings.cache_clear()
    seed_memory_database(database_url)

    router = FakeRouter()
    response = await generate_chat_response(make_event(), router=router)

    assert "可参考的长期记忆" not in router.messages[0].content
    assert response.metadata["memory_injection_enabled"] is False
    assert response.metadata["memory_count"] == 0
    assert response.metadata["used_memory_ids"] == []
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_generate_chat_response_records_conversation(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'kaka-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_settings.cache_clear()

    event = make_event()
    response = await generate_chat_response(event, router=FakeRouter())

    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        user = session.scalar(select(UserRecord))
        scene = session.scalar(select(SceneRecord))
        input_record = session.scalar(select(InputRecord))
        saved_output = session.scalar(select(OutputRecord))

    assert user is not None
    assert user.platform_user_id == "10001"
    assert scene is not None
    assert scene.scene_id == "10001"
    assert input_record is not None
    assert input_record.event_id == event.event_id
    assert input_record.content_text == "你好"
    assert input_record.analysis_status == "not_analyzed"
    assert saved_output is not None
    assert saved_output.output_id == response.response_id
    assert saved_output.input_id == input_record.id
    assert saved_output.scene_id == scene.id
    assert saved_output.user_id == user.id
    assert saved_output.output_origin == "passive"
    assert saved_output.output_reason == "unknown"
    assert saved_output.content_text == "我在，刚刚听见了。"
    get_settings.cache_clear()


def test_observe_message_records_message_without_response(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'observe-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    event = make_event()

    response = observe_message(event)

    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        input_record = session.scalar(select(InputRecord))
        saved_output = session.scalar(select(OutputRecord))

    assert response.should_reply is False
    assert response.metadata["reason"] == "observed"
    assert input_record is not None
    assert input_record.event_id == event.event_id
    assert input_record.analysis_status == "not_analyzed"
    assert saved_output is None
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_duplicate_chat_event_reuses_existing_output(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'dedupe-chat-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_settings.cache_clear()

    event = make_event()
    router = FakeRouter()
    first_response = await generate_chat_response(event, router=router)
    second_response = await generate_chat_response(event, router=router)

    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        inputs = session.scalars(select(InputRecord)).all()
        outputs = session.scalars(select(OutputRecord)).all()

    assert router.calls == 1
    assert len(inputs) == 1
    assert len(outputs) == 1
    assert second_response.response_id == first_response.response_id
    assert second_response.metadata["deduplicated"] is True
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_concurrent_duplicate_chat_event_reuses_single_llm_call(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'concurrent-dedupe-chat-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_settings.cache_clear()

    event = make_event()
    router = SlowFakeRouter()
    first_response, second_response = await asyncio.gather(
        generate_chat_response(event, router=router),
        generate_chat_response(event, router=router),
    )

    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        inputs = session.scalars(select(InputRecord)).all()
        outputs = session.scalars(select(OutputRecord)).all()

    assert router.calls == 1
    assert len(inputs) == 1
    assert len(outputs) == 1
    assert second_response.response_id == first_response.response_id
    assert {first_response.metadata.get("deduplicated"), second_response.metadata.get("deduplicated")} == {
        None,
        True,
    }
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_concurrent_duplicate_chat_event_is_deduped_by_database_lock(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'db-lock-dedupe-chat-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    get_settings.cache_clear()

    event = make_event()
    router = SlowFakeRouter()

    async def bypass_acquire_event_lock(_event_id: str) -> BypassLockState:
        return BypassLockState()

    async def bypass_release_event_lock(_event_id: str, _state: BypassLockState) -> None:
        return None

    monkeypatch.setattr("kaka_core.chat.service.acquire_event_lock", bypass_acquire_event_lock)
    monkeypatch.setattr("kaka_core.chat.service.release_event_lock", bypass_release_event_lock)

    first_response, second_response = await asyncio.gather(
        generate_chat_response(event, router=router),
        generate_chat_response(event, router=router),
    )

    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        inputs = session.scalars(select(InputRecord)).all()
        outputs = session.scalars(select(OutputRecord)).all()

    assert router.calls == 1
    assert len(inputs) == 1
    assert len(outputs) == 1
    assert second_response.response_id == first_response.response_id
    assert {first_response.metadata.get("deduplicated"), second_response.metadata.get("deduplicated")} == {
        None,
        True,
    }
    get_settings.cache_clear()


def test_observe_does_not_reset_analyzed_input(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'observe-status-test.sqlite3'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()

    event = make_event()
    observe_message(event)
    engine = create_database_engine(database_url)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        input_record = session.scalar(select(InputRecord))
        assert input_record is not None
        input_record.analysis_status = "skipped"
        session.commit()

    observe_message(event)

    with session_factory() as session:
        input_record = session.scalar(select(InputRecord))

    assert input_record is not None
    assert input_record.analysis_status == "skipped"
    get_settings.cache_clear()


def seed_memory_database(database_url: str) -> None:
    engine = create_database_engine(database_url)
    init_database(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        user = UserRecord(
            platform="qq",
            platform_user_id="10001",
            display_name="主人",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        scene = SceneRecord(
            platform="qq",
            scene_type="private",
            scene_id="10001",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add_all([user, scene])
        session.flush()
        session.add(
            MemoryRecord(
                user_id=user.id,
                scene_id=scene.id,
                memory_text="我喜欢回复先给结论。",
                normalized_text="我喜欢回复先给结论",
                memory_type="stable_preference",
                confidence=0.9,
                source_text="回复时先给结论。",
                source="candidate",
                status="active",
                merge_reason="测试记忆",
                created_at=utc_now(),
                updated_at=utc_now(),
            )
        )
        session.commit()
