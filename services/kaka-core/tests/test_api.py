import httpx
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


def test_notification_rejects_missing_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-auth.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "secret-token")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    get_settings.cache_clear()

    request = {
        "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
    }

    response = client.post("/v1/notifications", json=request)

    assert response.status_code == 401
    get_settings.cache_clear()


def test_notification_returns_503_when_token_unconfigured(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-unconfigured.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    get_settings.cache_clear()

    request = {
        "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
    }

    response = client.post(
        "/v1/notifications",
        headers={"Authorization": "Bearer secret-token"},
        json=request,
    )

    assert response.status_code == 503
    get_settings.cache_clear()


def test_notification_rejects_unsupported_platform(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-platform.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "secret-token")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    get_settings.cache_clear()

    request = {
        "target": {"platform": "desktop", "scene_type": "private", "scene_id": "desktop-local"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
    }

    response = client.post(
        "/v1/notifications",
        headers={"Authorization": "Bearer secret-token"},
        json=request,
    )

    assert response.status_code == 400
    assert "unsupported notification platform" in response.json()["detail"]
    get_settings.cache_clear()


def test_notification_forwards_to_qq_adapter(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'notification-forward.sqlite3'}")
    monkeypatch.setenv("PLUGIN_NOTIFICATION_TOKEN", "secret-token")
    monkeypatch.setenv("QQ_ADAPTER_SEND_BASE_URL", "http://qq-adapter.local")
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    captured: dict[str, object] = {}
    original_post = httpx.Client.post

    def fake_post(self: httpx.Client, url: str, **kwargs: object) -> httpx.Response:
        if url == "/v1/notifications":
            return original_post(self, url, **kwargs)
        captured["url"] = url
        captured["headers"] = kwargs.get("headers")
        captured["json"] = kwargs.get("json")
        return httpx.Response(
            200,
            json={
                "accepted": True,
                "delivered": True,
                "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
                "metadata": {"adapter": "qq"},
            },
        )

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    request = {
        "target": {"platform": "qq", "scene_type": "group", "scene_id": "20002"},
        "content": {"type": "text", "text": "GitHub 周报"},
        "source": "n8n:github_weekly_stars",
        "idempotency_key": "github-weekly-stars:2026-06-08:qq:group:20002",
    }

    response = client.post(
        "/v1/notifications",
        headers={"Authorization": "Bearer secret-token"},
        json=request,
    )

    assert response.status_code == 200
    assert response.json()["delivered"] is True
    assert captured["url"] == "http://qq-adapter.local/v1/send"
    assert captured["headers"] == {"Authorization": "Bearer qq-send-token"}
    assert captured["json"] == request
    get_settings.cache_clear()
