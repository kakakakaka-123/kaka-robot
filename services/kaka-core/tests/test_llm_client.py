import pytest

from kaka_core.config.settings import LLMSettings, get_settings
from kaka_core.llm.client import ChatMessage, LLMClient


def make_llm_settings(*, request_timeout_seconds: float = 12.5) -> LLMSettings:
    return LLMSettings(
        enabled=True,
        api_key="test-key",
        base_url="https://example.test",
        chat_model="chat-model",
        reasoning_model="reasoning-model",
        memory_model="memory-model",
        tool_model="tool-model",
        temperature=0.7,
        max_tokens=100,
        request_timeout_seconds=request_timeout_seconds,
    )


def test_settings_reads_llm_request_timeout(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'settings.sqlite3'}")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "23.5")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.llm.request_timeout_seconds == 23.5
    get_settings.cache_clear()


@pytest.mark.anyio
async def test_llm_client_uses_configured_request_timeout(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "卡咔收到。"}}]}

    class FakeAsyncClient:
        def __init__(self, *, timeout: object) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def post(self, url: str, *, headers: dict, json: dict) -> FakeResponse:
            captured["url"] = url
            captured["payload"] = json
            return FakeResponse()

    monkeypatch.setattr("kaka_core.llm.client.httpx.AsyncClient", FakeAsyncClient)
    client = LLMClient(make_llm_settings(request_timeout_seconds=12.5))

    reply = await client.chat([ChatMessage(role="user", content="你好")])

    assert reply == "卡咔收到。"
    assert captured["timeout"] == 12.5
