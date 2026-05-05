from __future__ import annotations

from dataclasses import dataclass

from kaka_core.config.settings import (
    MemoryReplySettings,
    PersonaSettings,
    RelationshipSettings,
    ShortContextSettings,
)
from kaka_core.context.recent import ShortContextItem, format_short_context, load_short_context
from kaka_core.llm.client import ChatMessage
from kaka_core.memory.search import MemorySearchFilters, MemorySearchResult, search_user_memories
from kaka_core.persona.prompt import PersonaPrompt, load_persona_prompt
from kaka_core.relationship.context import RelationshipContext, load_relationship_context
from kaka_core.storage.database import create_session_factory, init_database
from kaka_protocol import MessageEvent


@dataclass(frozen=True)
class ReplyContextLayer:
    """回复上下文的一层。

    `name` 是稳定机器名，`role` 决定最终进入 system 还是 user 消息。
    """

    name: str
    title: str
    role: str
    content: str


@dataclass(frozen=True)
class ReplyContext:
    """一次回复前组装好的模型上下文。

    动态上下文统一拆成 layer，再合并成真正发给模型的 messages。
    后续情绪、用户画像、工具结果等新增上下文，也应该先成为独立 layer。
    """

    messages: tuple[ChatMessage, ...]
    metadata: dict[str, object]
    layers: tuple[ReplyContextLayer, ...]
    memories: tuple[MemorySearchResult, ...] = ()
    short_context: tuple[ShortContextItem, ...] = ()
    relationship: RelationshipContext | None = None
    persona: PersonaPrompt | None = None


def build_reply_context(
    event: MessageEvent,
    memory_settings: MemoryReplySettings,
    short_context_settings: ShortContextSettings,
    relationship_settings: RelationshipSettings,
    persona_settings: PersonaSettings,
) -> ReplyContext:
    """组装聊天模型输入。

    当前分层为 persona、relationship、memory、recent_context 和 current_message。
    这样后续添加 emotion、user_profile 等层时，不需要把逻辑塞进聊天服务。
    """

    user_text = event.content.text or ""
    persona_prompt = load_persona_prompt(persona_settings)
    memory_results, memory_metadata = load_memory_context(event, user_text, memory_settings)
    short_context_items, short_context_metadata = load_short_context_safely(
        event,
        user_text,
        short_context_settings,
    )
    relationship_context, relationship_metadata = load_relationship_context_safely(
        event,
        relationship_settings,
    )

    speaker_name = event.display_name or event.user_id
    layers = build_reply_context_layers(
        persona_prompt,
        memory_results,
        short_context_items,
        event,
        user_text,
        speaker_name,
        relationship_context,
    )
    messages = build_messages_from_layers(layers)
    metadata: dict[str, object] = {
        "context_layer_names": [layer.name for layer in layers],
        "context_layer_count": len(layers),
        "persona_prompt_source": persona_prompt.source,
        "persona_prompt_path": persona_prompt.path,
        "persona_prompt_fallback_used": persona_prompt.fallback_used,
        "memory_injection_enabled": memory_settings.enabled,
        "memory_count": len(memory_results),
        "used_memory_ids": [result.memory.id for result in memory_results],
    }
    if persona_prompt.error:
        metadata["persona_prompt_error"] = persona_prompt.error
    metadata.update(memory_metadata)
    metadata.update(short_context_metadata)
    metadata.update(relationship_metadata)

    return ReplyContext(
        messages=messages,
        metadata=metadata,
        layers=tuple(layers),
        memories=tuple(memory_results),
        short_context=tuple(short_context_items),
        relationship=relationship_context,
        persona=persona_prompt,
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


def load_short_context_safely(
    event: MessageEvent,
    user_text: str,
    short_context_settings: ShortContextSettings,
) -> tuple[list[ShortContextItem], dict[str, object]]:
    """读取短期上下文。

    短期上下文读取失败不能影响聊天主流程，因此这里会把异常降级为 metadata。
    """

    if not user_text.strip():
        return [], {
            "short_context_enabled": short_context_settings.enabled,
            "short_context_count": 0,
            "short_context_input_ids": [],
        }

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            return load_short_context(session, event, short_context_settings)
    except Exception as exc:  # noqa: BLE001
        return [], {
            "short_context_enabled": short_context_settings.enabled,
            "short_context_count": 0,
            "short_context_input_ids": [],
            "short_context_error": str(exc),
        }


def load_relationship_context_safely(
    event: MessageEvent,
    relationship_settings: RelationshipSettings,
) -> tuple[RelationshipContext | None, dict[str, object]]:
    """读取当前说话者关系上下文。

    关系上下文失败不能影响聊天主流程，因此这里会把异常降级到 metadata。
    """

    try:
        init_database()
        session_factory = create_session_factory()
        with session_factory() as session:
            relationship = load_relationship_context(session, event, relationship_settings)
    except Exception as exc:  # noqa: BLE001
        return None, {
            "relationship_level": "unknown",
            "relationship_error": str(exc),
        }

    return relationship, {
        "relationship_level": relationship.level,
        "relationship_is_owner": relationship.is_owner,
        "relationship_input_count": relationship.input_count,
        "relationship_recent_input_count": relationship.recent_input_count,
        "relationship_active_memory_count": relationship.active_memory_count,
        "relationship_recent_days": relationship.recent_days,
    }


def build_reply_context_layers(
    persona_prompt: PersonaPrompt,
    memory_results: list[MemorySearchResult],
    short_context_items: list[ShortContextItem],
    event: MessageEvent,
    user_text: str,
    speaker_name: str,
    relationship: RelationshipContext | None,
) -> tuple[ReplyContextLayer, ...]:
    layers: list[ReplyContextLayer] = [
        ReplyContextLayer(
            name="persona",
            title="基础人设",
            role="system",
            content=persona_prompt.content.rstrip(),
        )
    ]
    if relationship is not None:
        layers.append(
            ReplyContextLayer(
                name="relationship",
                title="关系上下文",
                role="system",
                content=build_relationship_prompt(relationship, speaker_name),
            )
        )
    memory_prompt = build_memory_prompt(memory_results, speaker_name)
    if memory_prompt:
        layers.append(
            ReplyContextLayer(
                name="memory",
                title="长期记忆",
                role="system",
                content=memory_prompt,
            )
        )
    recent_context_prompt = build_recent_context_prompt(short_context_items)
    if recent_context_prompt:
        layers.append(
            ReplyContextLayer(
                name="recent_context",
                title="短期上下文",
                role="user",
                content=recent_context_prompt,
            )
        )
    layers.append(
        ReplyContextLayer(
            name="current_message",
            title="当前消息",
            role="user",
            content=build_current_message_prompt(event, user_text),
        )
    )
    return tuple(layers)


def build_messages_from_layers(layers: tuple[ReplyContextLayer, ...]) -> tuple[ChatMessage, ...]:
    system_parts = [layer.content for layer in layers if layer.role == "system" and layer.content]
    user_parts = [layer.content for layer in layers if layer.role == "user" and layer.content]
    return (
        ChatMessage(role="system", content="\n".join(system_parts).rstrip() + "\n"),
        ChatMessage(role="user", content="\n\n".join(user_parts).rstrip()),
    )


def build_system_prompt(
    persona_prompt: PersonaPrompt,
    memory_results: list[MemorySearchResult],
    speaker_name: str,
    relationship: RelationshipContext | None,
) -> str:
    """兼容测试和脚本的 system prompt 构造入口。"""

    layers: list[ReplyContextLayer] = [
        ReplyContextLayer(
            name="persona",
            title="基础人设",
            role="system",
            content=persona_prompt.content.rstrip(),
        )
    ]
    if relationship is not None:
        layers.append(
            ReplyContextLayer(
                name="relationship",
                title="关系上下文",
                role="system",
                content=build_relationship_prompt(relationship, speaker_name),
            )
        )
    memory_prompt = build_memory_prompt(memory_results, speaker_name)
    if memory_prompt:
        layers.append(
            ReplyContextLayer(
                name="memory",
                title="长期记忆",
                role="system",
                content=memory_prompt,
            )
        )
    return build_messages_from_layers(layers)[0].content


def build_memory_prompt(memory_results: list[MemorySearchResult], speaker_name: str) -> str:
    if not memory_results:
        return ""
    lines = [
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


def build_relationship_prompt(
    relationship: RelationshipContext,
    speaker_name: str,
) -> str:
    label_map = {
        "owner": "主人 / 最亲近的维护者",
        "familiar": "熟人",
        "regular": "普通熟悉群友",
        "stranger": "陌生人或新近出现的人",
    }
    lines: list[str] = [
        f"当前说话者关系：{label_map.get(relationship.level, relationship.level)}（{speaker_name}）。",
        (
            "关系信号："
            f"历史输入 {relationship.input_count} 条，"
            f"最近 {relationship.recent_days} 天输入 {relationship.recent_input_count} 条，"
            f"active 正式记忆 {relationship.active_memory_count} 条。"
        ),
        "关系使用规则：",
    ]
    if relationship.level == "owner":
        lines.extend(
            [
                "- 这是卡咔最亲近的平等朋友和维护者，不要把对方当陌生人。",
                "- 可以更自然、更信任，但不要表现成主仆关系。",
            ]
        )
    elif relationship.level == "familiar":
        lines.extend(
            [
                "- 对方和卡咔已有较多互动，可以稍微自然一点。",
                "- 可以参考过往互动，但不要突然过度亲密。",
            ]
        )
    elif relationship.level == "regular":
        lines.extend(
            [
                "- 对方和卡咔有一些互动，保持自然礼貌即可。",
                "- 不要装作特别熟，也不要过度疏远。",
            ]
        )
    else:
        lines.extend(
            [
                "- 对方目前仍按陌生人或新人处理。",
                "- 保持礼貌和边界感，不要套近乎或主动表现得很亲密。",
            ]
        )
    return "\n".join(lines)


def build_relationship_prompt_lines(
    relationship: RelationshipContext,
    speaker_name: str,
) -> list[str]:
    """兼容旧测试和临时脚本。"""

    return ["", *build_relationship_prompt(relationship, speaker_name).splitlines()]


def build_recent_context_prompt(short_context_items: list[ShortContextItem] | None = None) -> str:
    if not short_context_items:
        return ""
    return "\n".join(
        [
            "近期对话（从旧到新，供理解上下文，不要机械复述）：",
            format_short_context(short_context_items),
        ]
    )


def build_current_message_prompt(
    event: MessageEvent,
    user_text: str,
) -> str:
    display_name = event.display_name or event.user_id
    scene_hint = f"当前场景：{event.platform}/{event.scene_type}，说话的人：{display_name}。"
    return f"{scene_hint}\n当前用户消息：{user_text}"


def build_user_prompt(
    event: MessageEvent,
    user_text: str,
    short_context_items: list[ShortContextItem] | None = None,
) -> str:
    """兼容测试和脚本的 user prompt 构造入口。"""

    parts = [
        build_recent_context_prompt(short_context_items),
        build_current_message_prompt(event, user_text),
    ]
    return "\n\n".join(part for part in parts if part)
