import nonebot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment

try:
    nonebot.get_driver()
except ValueError:
    nonebot.init()

from qq_adapter.nonebot_plugins.kaka_chat import (
    _classify_message_handling,
    _event_to_onebot_raw_event,
    _extract_text_for_core,
    _is_at_bot,
)
from qq_adapter.trigger import should_handle_group_plaintext


def test_group_plaintext_containing_kaka_should_be_handled() -> None:
    assert should_handle_group_plaintext("卡咔在吗") is True


def test_group_plaintext_without_kaka_should_not_be_handled() -> None:
    assert should_handle_group_plaintext("今天吃什么") is False


def test_group_plaintext_without_kaka_should_be_observed() -> None:
    event = GroupMessageEvent(
        time=1777570849,
        self_id=1537786366,
        post_type="message",
        sub_type="normal",
        user_id=2940667688,
        message_type="group",
        message_id=5775,
        message=Message([MessageSegment.text("今天吃什么")]),
        original_message=Message([MessageSegment.text("今天吃什么")]),
        raw_message="今天吃什么",
        font=0,
        sender={"nickname": "无妄生欢", "card": ""},
        group_id=1057020972,
    )

    class FakeBot:
        self_id = 1537786366

    handling = _classify_message_handling(FakeBot(), event)

    assert handling is not None
    assert handling.should_reply is False
    assert handling.output_origin == "none"
    assert handling.output_reason == "none"


def test_nonebot_event_to_raw_event_uses_plaintext() -> None:
    event = GroupMessageEvent(
        time=1777570849,
        self_id=1537786366,
        post_type="message",
        sub_type="normal",
        user_id=2940667688,
        message_type="group",
        message_id=5776,
        message=Message([MessageSegment.text("卡咔晚上好")]),
        original_message=Message([MessageSegment.text("卡咔晚上好")]),
        raw_message="卡咔晚上好",
        font=0,
        sender={"nickname": "无妄生欢", "card": ""},
        group_id=1057020972,
    )

    raw_event = _event_to_onebot_raw_event(event)

    assert raw_event["message"] == "卡咔晚上好"


def test_at_message_can_be_detected_and_text_is_extracted() -> None:
    event = GroupMessageEvent(
        time=1777570849,
        self_id=1537786366,
        post_type="message",
        sub_type="normal",
        user_id=2940667688,
        message_type="group",
        message_id=5777,
        message=Message(
            [
                MessageSegment.at(1537786366),
                MessageSegment.text(" 你好"),
            ]
        ),
        original_message=Message(
            [
                MessageSegment.at(1537786366),
                MessageSegment.text(" 你好"),
            ]
        ),
        raw_message="[CQ:at,qq=1537786366] 你好",
        font=0,
        sender={"nickname": "无妄生欢", "card": ""},
        group_id=1057020972,
    )

    class FakeBot:
        self_id = 1537786366

    assert _is_at_bot(FakeBot(), event) is True
    assert _extract_text_for_core(event, FakeBot()) == "你好"


def test_at_message_can_be_detected_from_raw_message() -> None:
    event = GroupMessageEvent(
        time=1777570849,
        self_id=1537786366,
        post_type="message",
        sub_type="normal",
        user_id=2940667688,
        message_type="group",
        message_id=5778,
        message=Message([MessageSegment.text("[at:qq=1537786366] 你好啊")]),
        original_message=Message([MessageSegment.text("[at:qq=1537786366] 你好啊")]),
        raw_message="[at:qq=1537786366] 你好啊",
        font=0,
        sender={"nickname": "无妄生欢", "card": ""},
        group_id=1057020972,
    )

    class FakeBot:
        self_id = 1537786366

    assert _is_at_bot(FakeBot(), event) is True


def test_at_only_message_uses_fallback_text() -> None:
    event = GroupMessageEvent(
        time=1777570849,
        self_id=1537786366,
        post_type="message",
        sub_type="normal",
        user_id=2940667688,
        message_type="group",
        message_id=5779,
        message=Message([MessageSegment.at(1537786366)]),
        original_message=Message([MessageSegment.at(1537786366)]),
        raw_message="[CQ:at,qq=1537786366]",
        font=0,
        sender={"nickname": "无妄生欢", "card": ""},
        group_id=1057020972,
    )

    class FakeBot:
        self_id = 1537786366

    raw_event = _event_to_onebot_raw_event(event, FakeBot())

    assert _is_at_bot(FakeBot(), event) is True
    assert _extract_text_for_core(event, FakeBot()) == "用户 @ 了卡咔。"
    assert raw_event["message"] == "用户 @ 了卡咔。"


def test_at_other_user_without_text_is_observed_as_neutral_text() -> None:
    event = GroupMessageEvent(
        time=1777570849,
        self_id=1537786366,
        post_type="message",
        sub_type="normal",
        user_id=2940667688,
        message_type="group",
        message_id=5780,
        message=Message([MessageSegment.at(2972632399)]),
        original_message=Message([MessageSegment.at(2972632399)]),
        raw_message="[CQ:at,qq=2972632399]",
        font=0,
        sender={"nickname": "无妄生欢", "card": ""},
        group_id=1057020972,
    )

    class FakeBot:
        self_id = 1537786366

    raw_event = _event_to_onebot_raw_event(event, FakeBot())

    assert _is_at_bot(FakeBot(), event) is False
    assert _extract_text_for_core(event, FakeBot()) == "用户 @ 了其他人。"
    assert raw_event["message"] == "用户 @ 了其他人。"
