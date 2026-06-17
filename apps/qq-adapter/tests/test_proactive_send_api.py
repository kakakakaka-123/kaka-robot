from collections.abc import Iterator

import pytest
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
from qq_adapter.sender import send_notification_request


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


def _message_to_text(message: object) -> str:
    """把 MessageSegment 或纯字符串统一成文本，方便断言发送内容。"""

    data = getattr(message, "data", None)
    if isinstance(data, dict) and "text" in data:
        return str(data["text"])
    return str(message)


class FakeBot:
    def __init__(self) -> None:
        self.group_messages: list[tuple[int, str]] = []
        self.private_messages: list[tuple[int, str]] = []

    async def send_group_msg(self, *, group_id: int, message: object) -> None:
        self.group_messages.append((group_id, _message_to_text(message)))

    async def send_private_msg(self, *, user_id: int, message: object) -> None:
        self.private_messages.append((user_id, _message_to_text(message)))


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
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post("/v1/send", json=make_request().model_dump(mode="json"))

    assert response.status_code == 401
    assert fake_bot.group_messages == []


def test_send_api_rejects_missing_token_before_body_validation(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        content=b"{not-json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401
    assert fake_bot.group_messages == []


def test_send_api_rejects_wrong_token(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer wrong-token"},
        json=make_request().model_dump(mode="json"),
    )

    assert response.status_code == 401
    assert fake_bot.group_messages == []


def test_send_api_rejects_wrong_token_before_body_validation(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        content=b"{not-json",
        headers={
            "Authorization": "Bearer wrong-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 401
    assert fake_bot.group_messages == []


def test_send_api_accepts_valid_token_before_rejecting_malformed_body(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        content=b"{not-json",
        headers={
            "Authorization": "Bearer qq-send-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422
    assert fake_bot.group_messages == []


def test_send_api_returns_503_when_token_unconfigured(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post("/v1/send", json=make_request().model_dump(mode="json"))

    assert response.status_code == 503
    assert fake_bot.group_messages == []


def test_send_api_returns_503_when_token_unconfigured_before_body_validation(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        content=b"{not-json",
        headers={
            "Authorization": "Bearer qq-send-token",
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 503
    assert fake_bot.group_messages == []


def test_send_api_returns_503_when_bot_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")

    def get_unavailable_bot() -> FakeBot:
        raise RuntimeError("no OneBot connection is available")

    client = TestClient(
        create_send_api(get_unavailable_bot),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request().model_dump(mode="json"),
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "no OneBot connection is available"


def test_send_api_sends_group_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
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


def test_send_api_sends_private_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
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


def test_send_api_rejects_non_qq_platform(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(platform=Platform.WEB).model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []


def test_send_api_rejects_empty_text(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(text="").model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []


def test_send_api_rejects_non_text_content(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
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


def test_send_api_rejects_unsupported_qq_scene_type(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(scene_type=SceneType.ROOM).model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []
    assert fake_bot.private_messages == []


def test_send_api_rejects_non_numeric_scene_id(monkeypatch) -> None:
    monkeypatch.setenv("QQ_ADAPTER_SEND_TOKEN", "qq-send-token")
    fake_bot = FakeBot()
    client = TestClient(create_send_api(lambda: fake_bot))

    response = client.post(
        "/v1/send",
        headers={"Authorization": "Bearer qq-send-token"},
        json=make_request(scene_id="not-a-number").model_dump(mode="json"),
    )

    assert response.status_code == 400
    assert fake_bot.group_messages == []


@pytest.mark.anyio
async def test_sender_sends_group_text_without_api_dependency() -> None:
    fake_bot = FakeBot()

    await send_notification_request(fake_bot, make_request())

    assert fake_bot.group_messages == [(20002, "GitHub weekly stars")]


@pytest.mark.anyio
async def test_sender_escapes_cq_codes_in_text() -> None:
    """通知文本里的 CQ 码必须被当作纯文本，不能触发 @全体 等行为。"""

    fake_bot = FakeBot()
    payload = "[CQ:at,qq=all] 大家看周报"

    await send_notification_request(
        fake_bot,
        make_request(text=payload),
    )

    # 发出的应是 MessageSegment.text，data.text 保留原始文本，不被解析成 CQ 码。
    assert len(fake_bot.group_messages) == 1
    group_id, sent_text = fake_bot.group_messages[0]
    assert group_id == 20002
    assert sent_text == payload
