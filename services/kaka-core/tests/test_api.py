from fastapi.testclient import TestClient

from kaka_core.api.app import create_app
from kaka_core.config.settings import get_settings
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType


client = TestClient(create_app())


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "kaka-core"}


def test_chat_accepts_message_event_and_returns_kaka_response(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'api-test.sqlite3'}")
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    get_settings.cache_clear()
    event = MessageEvent(
        platform=Platform.QQ,
        scene_type=SceneType.GROUP,
        scene_id="20002",
        user_id="10001",
        display_name="群友A",
        content=MessageContent.text_message("卡咔在吗"),
    )

    response = client.post("/v1/chat", json=event.model_dump(mode="json"))
    data = response.json()

    assert response.status_code == 200
    assert data["event_id"] == event.event_id
    assert data["should_reply"] is True
    assert data["actions"][0]["type"] == "send_text"
    assert data["actions"][0]["content"]["type"] == "text"
    assert data["actions"][0]["content"]["text"] == "收到 群友A 的消息：卡咔在吗"
    assert data["metadata"]["fallback_reason"] == "llm_disabled_or_missing_key"
    get_settings.cache_clear()


def test_observe_accepts_message_event_and_does_not_reply(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'observe-api-test.sqlite3'}")
    get_settings.cache_clear()
    event = MessageEvent(
        platform=Platform.QQ,
        scene_type=SceneType.GROUP,
        scene_id="20002",
        user_id="10001",
        display_name="群友A",
        content=MessageContent.text_message("今天吃什么"),
    )

    response = client.post("/v1/observe", json=event.model_dump(mode="json"))
    data = response.json()

    assert response.status_code == 200
    assert data["event_id"] == event.event_id
    assert data["should_reply"] is False
    assert data["actions"] == []
    assert data["metadata"]["reason"] == "observed"
    get_settings.cache_clear()
