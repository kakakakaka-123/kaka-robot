import pytest

from kaka_protocol import KakaResponse, MessageEvent
from qq_adapter.pipeline import handle_onebot_text_event


class FakeCoreClient:
    """测试用卡咔核心服务客户端，不访问真实服务。"""

    def __init__(self) -> None:
        self.observed_event: MessageEvent | None = None

    async def chat(self, event: MessageEvent) -> KakaResponse:
        assert event.scene_id == "20002"
        assert event.content.text == "卡咔在吗"
        return KakaResponse.text_reply("我在。", event_id=event.event_id)

    async def observe(self, event: MessageEvent) -> KakaResponse:
        self.observed_event = event
        return KakaResponse.no_reply(event_id=event.event_id, reason="observed")


@pytest.mark.anyio
async def test_handle_onebot_text_event() -> None:
    actions = await handle_onebot_text_event(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 123,
            "group_id": 20002,
            "user_id": 10001,
            "sender": {"nickname": "小明", "card": "群友A"},
            "message": "卡咔在吗",
        },
        core_client=FakeCoreClient(),
    )

    assert len(actions) == 1
    assert actions[0].scene_id == "20002"
    assert actions[0].text == "我在。"


@pytest.mark.anyio
async def test_handle_onebot_text_event_can_observe_without_reply() -> None:
    client = FakeCoreClient()

    actions = await handle_onebot_text_event(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 124,
            "group_id": 20002,
            "user_id": 10001,
            "sender": {"nickname": "小明", "card": "群友A"},
            "message": "今天吃什么",
        },
        core_client=client,
        should_reply=False,
    )

    assert actions == []
    assert client.observed_event is not None
    assert "output_reason" not in client.observed_event.metadata
