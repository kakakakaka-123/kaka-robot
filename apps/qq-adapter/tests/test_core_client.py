import httpx
import pytest

from kaka_protocol import KakaResponse, MessageContent, MessageEvent, Platform, SceneType
from qq_adapter.config import QQAdapterSettings
from qq_adapter.core_client import KakaCoreClient, KakaCoreClientError


def make_event() -> MessageEvent:
    return MessageEvent(
        platform=Platform.QQ,
        scene_type=SceneType.GROUP,
        scene_id="20002",
        user_id="10001",
        display_name="群友A",
        content=MessageContent.text_message("卡咔在吗"),
    )


@pytest.mark.anyio
async def test_core_client_posts_message_event(monkeypatch) -> None:
    captured_json = None
    response_body = KakaResponse.text_reply("我在。", event_id=make_event().event_id)

    async def fake_post(self, url, json):
        nonlocal captured_json
        captured_json = json
        return httpx.Response(200, json=response_body.model_dump(mode="json"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = KakaCoreClient(
        QQAdapterSettings(
            core_base_url="http://127.0.0.1:8000",
            request_timeout_seconds=60,
        )
    )

    response = await client.chat(make_event())

    assert captured_json is not None
    assert captured_json["platform"] == "qq"
    assert response.actions[0].content is not None
    assert response.actions[0].content.text == "我在。"


@pytest.mark.anyio
async def test_core_client_posts_observe_event(monkeypatch) -> None:
    captured_url = None
    response_body = KakaResponse.no_reply(event_id=make_event().event_id, reason="observed")

    async def fake_post(self, url, json):
        nonlocal captured_url
        captured_url = url
        return httpx.Response(200, json=response_body.model_dump(mode="json"))

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = KakaCoreClient(
        QQAdapterSettings(
            core_base_url="http://127.0.0.1:8000",
            request_timeout_seconds=60,
        )
    )

    response = await client.observe(make_event())

    assert captured_url == "http://127.0.0.1:8000/v1/observe"
    assert response.should_reply is False
    assert response.metadata["reason"] == "observed"


@pytest.mark.anyio
async def test_core_client_wraps_connection_error(monkeypatch) -> None:
    async def fake_post(self, url, json):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    client = KakaCoreClient(
        QQAdapterSettings(
            core_base_url="http://127.0.0.1:8001",
            request_timeout_seconds=60,
        )
    )

    with pytest.raises(KakaCoreClientError, match="连接失败"):
        await client.chat(make_event())
