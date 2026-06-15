from kaka_protocol import (
    ActionType,
    ContentType,
    KakaResponse,
    MessageContent,
    MessageEvent,
    NotificationRequest,
    NotificationResult,
    NotificationTarget,
    Platform,
    ResponseAction,
    SceneType,
)


def test_qq_private_text_message_event_can_be_serialized() -> None:
    event = MessageEvent(
        platform=Platform.QQ,
        scene_type=SceneType.PRIVATE,
        scene_id="10001",
        user_id="10001",
        display_name="用户A",
        content=MessageContent.text_message("卡咔在吗"),
    )

    data = event.model_dump(mode="json")

    assert data["platform"] == "qq"
    assert data["scene_type"] == "private"
    assert data["content"]["type"] == "text"
    assert data["content"]["text"] == "卡咔在吗"


def test_qq_group_text_message_event_can_be_serialized() -> None:
    event = MessageEvent(
        platform=Platform.QQ,
        scene_type=SceneType.GROUP,
        scene_id="20002",
        user_id="10001",
        display_name="群友A",
        content=MessageContent(type=ContentType.TEXT, text="今天先做协议层"),
        raw_event={"message_id": 123},
    )

    data = event.model_dump(mode="json")

    assert data["scene_id"] == "20002"
    assert data["user_id"] == "10001"
    assert data["raw_event"]["message_id"] == 123


def test_text_response_can_be_serialized() -> None:
    response = KakaResponse.text_reply("我在。", event_id="event-1")

    data = response.model_dump(mode="json")

    assert data["event_id"] == "event-1"
    assert data["should_reply"] is True
    assert data["actions"][0]["type"] == "send_text"
    assert data["actions"][0]["content"]["text"] == "我在。"


def test_no_reply_response_can_be_serialized() -> None:
    response = KakaResponse.no_reply(event_id="event-1", reason="not_mentioned")

    data = response.model_dump(mode="json")

    assert data["should_reply"] is False
    assert data["actions"] == []
    assert data["metadata"]["reason"] == "not_mentioned"


def test_response_action_noop_keeps_reason() -> None:
    action = ResponseAction.noop("cooldown")

    assert action.type == ActionType.NOOP
    assert action.metadata["reason"] == "cooldown"


def test_notification_request_can_be_serialized() -> None:
    request = NotificationRequest(
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="20002",
        ),
        content=MessageContent.text_message("GitHub 周报"),
        source="n8n:github_weekly_stars",
        idempotency_key="github-weekly-stars:2026-06-08:qq:group:20002",
    )

    data = request.model_dump(mode="json")

    assert data["target"]["platform"] == "qq"
    assert data["target"]["scene_type"] == "group"
    assert data["target"]["scene_id"] == "20002"
    assert data["content"]["type"] == "text"
    assert data["content"]["text"] == "GitHub 周报"
    assert data["source"] == "n8n:github_weekly_stars"
    assert data["idempotency_key"] == "github-weekly-stars:2026-06-08:qq:group:20002"


def test_notification_result_can_be_serialized() -> None:
    result = NotificationResult(
        accepted=True,
        delivered=True,
        target=NotificationTarget(
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="20002",
        ),
        metadata={"adapter": "qq"},
    )

    data = result.model_dump(mode="json")

    assert data["accepted"] is True
    assert data["delivered"] is True
    assert data["target"]["platform"] == "qq"
    assert data["metadata"]["adapter"] == "qq"
