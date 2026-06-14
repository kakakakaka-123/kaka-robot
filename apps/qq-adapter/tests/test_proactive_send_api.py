from fastapi.testclient import TestClient

from kaka_protocol import (
    ContentType,
    MessageContent,
    NotificationRequest,
    NotificationTarget,
    Platform,
    SceneType,
)
from qq_adapter.api import create_send_api
from qq_adapter.config import get_settings


class FakeBot:
    def __init__(self) -> None:
        self.group_messages: list[tuple[int, str]] = []
        self.private_messages: list[tuple[int, str]] = []

    async def send_group_msg(self, *, group_id: int, message: str) -> None:
        self.group_messages.append((group_id, message))

    async def send_private_msg(self, *, user_id: int, message: str) -> None:
        self.private_messages.append((user_id, message))


def make_request(
    *,
    platform: Platform = Platform.QQ,
    scene_type: SceneType = SceneType.GROUP,
    scene_id: str = "20002",
    text: str = "GitHub weekly stars",
) -> NotificationRequest:
    return NotificationRequest(
        target=NotificationTarget(
            platform=platform,
            scene_type=scene_type,
            scene_id=scene_id,
        ),
        content=MessageContent.text_message(text),
        source="n8n:github_weekly_stars",
    )


def test_send_api_rejects_missing_token(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post("/v1/send", json=make_request().model_dump(mode="json"))

    assert response.status_code == 401
    assert fake_bot.group_messages == []
    get_settings.cache_clear()


def test_send_api_returns_503_when_token_unconfigured(monkeypatch) -> None:
    monkeypatch.delenv("QQ_ADAPTER_SEND_TOKEN", raising=False)
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post("/v1/send", json=make_request().model_dump(mode="json"))

    assert response.status_code == 503
    assert fake_bot.group_messages == []
    get_settings.cache_clear()


def test_send_api_sends_group_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request().model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert response.json()["delivered"] is True
    assert response.json()["target"]["scene_id"] == "20002"
    assert response.json()["metadata"] == {
        "adapter": "qq",
        "source": "n8n:github_weekly_stars",
    }
    assert fake_bot.group_messages == [(20002, "GitHub weekly stars")]
    get_settings.cache_clear()


def test_send_api_sends_private_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(
            scene_type=SceneType.PRIVATE,
            scene_id="10001",
        ).model_dump(mode="json"),
    )

    assert response.status_code == 200
    assert response.json()["delivered"] is True
    assert fake_bot.private_messages == [(10001, "GitHub weekly stars")]
    get_settings.cache_clear()


def test_send_api_rejects_non_qq_platform(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(platform=Platform.WEB).model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []
    get_settings.cache_clear()


def test_send_api_rejects_empty_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(text="").model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []
    get_settings.cache_clear()


def test_send_api_rejects_non_text_content(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    get_settings.cache_clear()
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))
    request = make_request()
    request.content = MessageContent(type=ContentType.IMAGE, text="not a text notification")

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=request.model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []
    get_settings.cache_clear()
