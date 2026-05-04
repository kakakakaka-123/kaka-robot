from __future__ import annotations

from dataclasses import dataclass

from kaka_core.config.settings import MemoryReplySettings
from kaka_core.llm.client import ChatMessage
from kaka_core.memory.search import MemorySearchFilters, MemorySearchResult, search_user_memories
from kaka_core.storage.database import create_session_factory, init_database
from kaka_protocol import MessageEvent


SYSTEM_PROMPT = """你是卡咔，一个正在成长中的 AI 人格体。
当前阶段你只需要完成自然、简洁的文字回复。

基础表达规则：
- 使用中文。
- 不要自称助手。
- 不要过度卖萌。
- 不要滥用 emoji。
- 回复要自然，像正在认真听对方说话。
"""


@dataclass(frozen=True)
class ReplyContext:
    """一次回复前组装好的模型上下文。

    后续情绪、关系、短期上下文、人设扩展都应该接到这里，而不是散落在
    chat service 里。
    """

    messages: tuple[ChatMessage, ...]
    metadata: dict[str, object]
    memories: tuple[MemorySearchResult, ...] = ()


def build_reply_context(
    event: MessageEvent,
    memory_settings: MemoryReplySettings,
) -> ReplyContext:
    """组装聊天模型输入。

    当前第一版只包含基础人设、长期记忆和当前消息；后续可以继续添加
    recent_context、emotion_context、relationship_context 等部分。
    """

    user_text = event.content.text or ""
    memory_results, memory_metadata = load_memory_context(event, user_text, memory_settings)

    speaker_name = event.display_name or event.user_id
    system_prompt = build_system_prompt(memory_results, speaker_name)
    user_prompt = build_user_prompt(event, user_text)
    metadata: dict[str, object] = {
        "memory_injection_enabled": memory_settings.enabled,
        "memory_count": len(memory_results),
        "used_memory_ids": [result.memory.id for result in memory_results],
    }
    metadata.update(memory_metadata)

    return ReplyContext(
        messages=(
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_prompt),
        ),
        metadata=metadata,
        memories=tuple(memory_results),
    )


def load_memory_context(
    event: MessageEvent,
    user_text: str,
    memory_settings: MemoryReplySettings,
) -> tuple[list[MemorySearchResult], dict[str, object]]:
    """读取当前回复可参考的长期记忆。

    记忆读取失败不能影响聊天主流程，因此这里会把异常降级为 metadata。
    """

    if not memory_settings.enabled or not user_text.strip():
        return [], {}

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            results = search_user_memories(
                session,
                MemorySearchFilters(
                    platform=str(event.platform),
                    user_id=event.user_id,
                    query_text=user_text,
                    limit=memory_settings.limit,
                    pool_size=memory_settings.pool_size,
                    min_score=memory_settings.min_score,
                    target_scene_type=str(event.scene_type),
                    target_scene_id=event.scene_id,
                ),
            )
    except Exception as exc:  # noqa: BLE001
        return [], {"memory_error": str(exc)}

    return results, {
        "memory_min_score": memory_settings.min_score,
        "memory_limit": memory_settings.limit,
    }


def build_system_prompt(memory_results: list[MemorySearchResult], speaker_name: str) -> str:
    if not memory_results:
        return SYSTEM_PROMPT

    lines = [
        SYSTEM_PROMPT.rstrip(),
        "",
        f"可参考的长期记忆（均描述当前说话用户：{speaker_name}，不是卡咔自己）：",
        "说明：记忆正文中的“我 / 我的 / 本人”默认指当前说话用户，不指卡咔。",
    ]
    for index, result in enumerate(memory_results, start=1):
        lines.append(f"{index}. 当前说话用户：{result.memory.memory_text}")
    lines.extend(
        [
            "",
            "使用长期记忆的规则：",
            "- 长期记忆只是背景，不要无关地主动提起。",
            "- 当前用户消息仍然是本次回复的核心。",
            "- 回答时要把长期记忆转换成正确人称，不要照抄记忆里的第一人称。",
            "- 不要把当前说话用户的身份、经历、偏好说成卡咔自己的身份、经历、偏好。",
            "- 如果记忆和当前消息无关，就自然忽略。",
        ]
    )
    return "\n".join(lines)


def build_user_prompt(event: MessageEvent, user_text: str) -> str:
    display_name = event.display_name or event.user_id
    scene_hint = f"当前场景：{event.platform}/{event.scene_type}，说话的人：{display_name}。"
    return f"{scene_hint}\n用户消息：{user_text}"
