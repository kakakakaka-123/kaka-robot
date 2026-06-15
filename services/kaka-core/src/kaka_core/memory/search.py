from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from kaka_core.storage.models import MemoryRecord, SceneRecord, UserRecord, utc_now

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
ACTIVE_MEMORY_STATUS = "active"
GENERAL_MEMORY_TYPES = {"stable_preference"}
REPLY_STYLE_PREFERENCE_TERMS = {
    "回复",
    "回答",
    "说话",
    "聊天",
    "语气",
    "称呼",
    "风格",
    "表达",
    "卡咔",
}

TYPE_WEIGHTS = {
    "stable_preference": 1.8,
    "user_fact": 1.2,
    "relationship_fact": 1.0,
    "important_event": 0.8,
}

CHINESE_STOP_TERMS = {
    "一个",
    "一下",
    "一些",
    "这个",
    "那个",
    "这里",
    "那里",
    "现在",
    "今天",
    "明天",
    "昨天",
    "继续",
    "然后",
    "就是",
    "如果",
    "因为",
    "所以",
    "可以",
    "需要",
    "已经",
    "没有",
    "不是",
    "还是",
    "什么",
    "怎么",
    "时候",
    "感觉",
    "觉得",
    "进行",
    "这个地方",
}

ASCII_STOP_TERMS = {
    "the",
    "and",
    "for",
    "with",
    "this",
    "that",
    "you",
    "are",
    "was",
    "were",
}


@dataclass(frozen=True)
class MemorySearchFilters:
    platform: str
    user_id: str
    query_text: str
    limit: int = 5
    pool_size: int = 300
    min_score: float = 1.0
    memory_type: str | None = None
    target_scene_type: str | None = None
    target_scene_id: str | None = None


@dataclass(frozen=True)
class MemorySearchResult:
    memory: MemoryRecord
    scene: SceneRecord | None
    score: float
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]


SearchFilters = MemorySearchFilters


def search_user_memories(
    session: Session,
    filters: MemorySearchFilters,
) -> list[MemorySearchResult]:
    """检索当前用户可用于回复上下文的正式长期记忆。"""

    user = load_user(session, filters)
    if user is None:
        return []
    rows = load_memory_pool(session, filters, user)
    return rank_memories(rows, filters)


def load_user(session: Session, filters: MemorySearchFilters) -> UserRecord | None:
    return session.scalar(
        select(UserRecord).where(
            UserRecord.platform == filters.platform,
            UserRecord.platform_user_id == filters.user_id,
        )
    )


def load_memory_pool(
    session: Session,
    filters: MemorySearchFilters,
    user: UserRecord,
) -> list[tuple[MemoryRecord, SceneRecord | None]]:
    statement = (
        select(MemoryRecord, SceneRecord)
        .outerjoin(SceneRecord, MemoryRecord.scene_id == SceneRecord.id)
        .where(
            MemoryRecord.user_id == user.id,
            MemoryRecord.status == ACTIVE_MEMORY_STATUS,
        )
        .order_by(MemoryRecord.updated_at.desc(), MemoryRecord.created_at.desc())
        .limit(filters.pool_size)
    )

    if filters.memory_type:
        statement = statement.where(MemoryRecord.memory_type == filters.memory_type)

    return list(session.execute(statement).all())


def rank_memories(
    rows: list[tuple[MemoryRecord, SceneRecord | None]],
    filters: MemorySearchFilters,
) -> list[MemorySearchResult]:
    query_terms = extract_terms(filters.query_text)
    scored = [score_memory(memory, scene, filters, query_terms) for memory, scene in rows]
    matched = [result for result in scored if result.score >= filters.min_score]
    matched.sort(key=sort_key)
    return matched[: filters.limit]


def sort_key(result: MemorySearchResult) -> tuple[float, float, int]:
    updated_at = result.memory.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return (-result.score, -updated_at.timestamp(), result.memory.id)


def score_memory(
    memory: MemoryRecord,
    scene: SceneRecord | None,
    filters: MemorySearchFilters,
    query_terms: set[str],
) -> MemorySearchResult:
    memory_terms = extract_terms(f"{memory.memory_text} {memory.source_text or ''}")
    matched_terms = tuple(sorted(query_terms & memory_terms, key=lambda item: (-len(item), item)))
    text_match_score, text_match_reasons = score_text_match(
        filters.query_text,
        memory,
        matched_terms,
    )

    general_without_text_match = text_match_score <= 0 and is_reply_style_general_memory(memory)
    if text_match_score <= 0 and not general_without_text_match:
        return MemorySearchResult(
            memory=memory,
            scene=scene,
            score=0.0,
            matched_terms=matched_terms,
            reasons=("无文本命中，默认不推荐",),
        )

    score = text_match_score
    reasons = list(text_match_reasons)
    if general_without_text_match:
        reasons.append("稳定回复偏好可作为常驻背景")

    scene_score, scene_reasons = score_scene(scene, filters)
    score += scene_score
    reasons.extend(scene_reasons)

    type_weight = TYPE_WEIGHTS.get(memory.memory_type, 0.5)
    score += type_weight
    reasons.append(f"类型权重：{memory.memory_type} +{type_weight:.1f}")

    confidence_score = max(0.0, min(float(memory.confidence), 1.0)) * 1.5
    score += confidence_score
    reasons.append(f"置信度：{memory.confidence:.2f} +{confidence_score:.1f}")

    recency_score = score_recency(memory.updated_at)
    if recency_score > 0:
        score += recency_score
        reasons.append(f"近期更新 +{recency_score:.1f}")

    return MemorySearchResult(
        memory=memory,
        scene=scene,
        score=round(score, 3),
        matched_terms=matched_terms,
        reasons=tuple(reasons),
    )


def score_text_match(
    query_text: str,
    memory: MemoryRecord,
    matched_terms: tuple[str, ...],
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []
    if matched_terms:
        match_score = min(len(matched_terms) * 1.5, 12.0)
        score += match_score
        preview = "、".join(matched_terms[:8])
        reasons.append(f"关键词命中：{preview} +{match_score:.1f}")

    normalized_query = normalize_for_substring(query_text)
    normalized_memory = normalize_for_substring(memory.memory_text)
    normalized_source = normalize_for_substring(memory.source_text or "")
    search_space = f"{normalized_memory} {normalized_source}"

    if normalized_query and len(normalized_query) >= 4 and normalized_query in search_space:
        score += 8.0
        reasons.append("当前消息完整命中记忆文本 +8.0")
    elif normalized_memory and len(normalized_memory) >= 4 and normalized_memory in normalized_query:
        score += 6.0
        reasons.append("记忆文本完整命中当前消息 +6.0")

    return score, reasons


def is_reply_style_general_memory(memory: MemoryRecord) -> bool:
    if memory.memory_type not in GENERAL_MEMORY_TYPES:
        return False
    text = f"{memory.memory_text} {memory.source_text or ''}"
    return any(term in text for term in REPLY_STYLE_PREFERENCE_TERMS)


def score_scene(
    scene: SceneRecord | None,
    filters: MemorySearchFilters,
) -> tuple[float, list[str]]:
    if scene is None or filters.target_scene_type is None or filters.target_scene_id is None:
        return 0.0, []
    if scene.scene_type == filters.target_scene_type and scene.scene_id == filters.target_scene_id:
        return 2.0, [f"同场景：{format_scene(scene)} +2.0"]
    if scene.scene_type == filters.target_scene_type:
        return 0.3, [f"同场景类型：{format_scene_type(scene.scene_type)} +0.3"]
    return 0.0, []


def score_recency(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    days = max(0, (utc_now() - value.astimezone(timezone.utc)).days)
    if days <= 7:
        return 0.6
    if days <= 30:
        return 0.4
    if days <= 90:
        return 0.2
    return 0.0


def extract_terms(value: str | None) -> set[str]:
    text = str(value or "").strip().lower()
    terms: set[str] = set()

    for word in re.findall(r"[a-z0-9][a-z0-9_.+-]{1,}", text):
        if word not in ASCII_STOP_TERMS:
            terms.add(word)

    for run in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(run) <= 8 and run not in CHINESE_STOP_TERMS:
            terms.add(run)
        max_size = min(4, len(run))
        for size in range(2, max_size + 1):
            for index in range(0, len(run) - size + 1):
                term = run[index : index + size]
                if term not in CHINESE_STOP_TERMS:
                    terms.add(term)

    return terms


def normalize_for_substring(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[。.!！?？~～…]+$", "", text)
    return text


def format_scene(scene: SceneRecord) -> str:
    scene_type = format_scene_type(scene.scene_type)
    return f"{scene.platform} / {scene_type} / {scene.scene_id}"


def format_scene_type(scene_type: str) -> str:
    scene_type_map = {
        "private": "私聊",
        "group": "群聊",
        "room": "房间",
        "device": "设备",
        "system": "系统",
    }
    return scene_type_map.get(scene_type, scene_type)


def format_local_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")
