from qq_adapter.actions import QQSendTextAction, response_to_qq_text_actions
from qq_adapter.core_client import KakaCoreClient
from qq_adapter.qq_event import onebot_event_to_message_event


async def handle_onebot_text_event(
    raw_event: dict,
    core_client: KakaCoreClient,
    *,
    should_reply: bool = True,
    output_origin: str = "passive",
    output_reason: str = "unknown",
) -> list[QQSendTextAction]:
    """处理一条 OneBot 文本事件。

    这是未来 NoneBot 插件会调用的核心流程：
    1. 原始 QQ 事件转成统一消息事件。
    2. 根据触发规则选择聊天回复或只观察记录。
    3. 把卡咔统一响应转成 QQ 侧发送动作。
    """

    message_event = onebot_event_to_message_event(raw_event)

    if should_reply:
        message_event.metadata["output_origin"] = output_origin
        message_event.metadata["output_reason"] = output_reason
        response = await core_client.chat(message_event)
    else:
        response = await core_client.observe(message_event)

    return response_to_qq_text_actions(response, default_scene_id=message_event.scene_id)
