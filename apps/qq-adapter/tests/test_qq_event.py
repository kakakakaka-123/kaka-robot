import pytest

from kaka_protocol import Platform, SceneType
from qq_adapter.qq_event import onebot_event_to_message_event


def test_group_text_event_to_message_event() -> None:
    event = onebot_event_to_message_event(
        {
            "post_type": "message",
            "message_type": "group",
            "message_id": 123,
            "group_id": 20002,
            "user_id": 10001,
            "sender": {"nickname": "小明", "card": "群友A"},
            "message": [{"type": "text", "data": {"text": "卡咔在吗"}}],
        }
    )

    assert event.platform == Platform.QQ
    assert event.scene_type == SceneType.GROUP
    assert event.scene_id == "20002"
    assert event.user_id == "10001"
    assert event.display_name == "群友A"
    assert event.event_id == "qq:group:20002:123"
    assert event.content.text == "卡咔在吗"
    assert event.metadata["qq_message_id"] == "123"


def test_private_text_event_to_message_event() -> None:
    event = onebot_event_to_message_event(
        {
            "post_type": "message",
            "message_type": "private",
            "message_id": 456,
            "user_id": 10001,
            "sender": {"nickname": "用户A"},
            "message": "你好",
        }
    )

    assert event.scene_type == SceneType.PRIVATE
    assert event.scene_id == "10001"
    assert event.display_name == "用户A"
    assert event.content.text == "你好"


def test_non_text_event_is_rejected() -> None:
    with pytest.raises(ValueError, match="非空文本消息"):
        onebot_event_to_message_event(
            {
                "post_type": "message",
                "message_type": "group",
                "group_id": 20002,
                "user_id": 10001,
                "message": [{"type": "image", "data": {"file": "a.png"}}],
            }
        )
