from dataclasses import dataclass

from kaka_protocol import ActionType, KakaResponse


@dataclass(frozen=True)
class QQSendTextAction:
    """QQ 侧待发送文本动作。

    第一版只处理文本发送。后续图片、语音、表情会扩展成更多动作类型。
    """

    scene_id: str
    text: str


def response_to_qq_text_actions(
    response: KakaResponse,
    default_scene_id: str,
) -> list[QQSendTextAction]:
    """把卡咔统一响应转换成 QQ 侧可发送的文本动作。"""

    if not response.should_reply:
        return []

    actions: list[QQSendTextAction] = []
    for action in response.actions:
        if action.type != ActionType.SEND_TEXT:
            continue
        if action.content is None or not action.content.text:
            continue
        actions.append(
            QQSendTextAction(
                scene_id=action.target_scene_id or default_scene_id,
                text=action.content.text,
            )
        )

    return actions
