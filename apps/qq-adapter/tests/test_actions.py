from kaka_protocol import KakaResponse

from qq_adapter.actions import response_to_qq_text_actions


def test_response_to_qq_text_actions() -> None:
    response = KakaResponse.text_reply("我在。", event_id="event-1")

    actions = response_to_qq_text_actions(response, default_scene_id="20002")

    assert len(actions) == 1
    assert actions[0].scene_id == "20002"
    assert actions[0].text == "我在。"


def test_no_reply_response_has_no_actions() -> None:
    response = KakaResponse.no_reply(event_id="event-1", reason="not_mentioned")

    actions = response_to_qq_text_actions(response, default_scene_id="20002")

    assert actions == []
