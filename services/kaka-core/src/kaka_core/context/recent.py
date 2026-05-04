from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from kaka_core.config.settings import ShortContextSettings
from kaka_core.storage.models import InputRecord, OutputRecord, SceneRecord, UserRecord
from kaka_protocol import MessageEvent


@dataclass(frozen=True)
class ShortContextItem:
    """一条可注入回复 prompt 的近期对话。"""

    input_id: int
    user_id: str
    display_name: str
    user_text: str
    kaka_text: str | None
    created_at: datetime


def load_short_context(
    session: Session,
    event: MessageEvent,
    settings: ShortContextSettings,
) -> tuple[list[ShortContextItem], dict[str, object]]:
    """读取同场景最近输入，作为短期上下文。

    第一版只按场景隔离，不做复杂用户画像。群聊取同群最近消息，私聊取同一私聊场景；
    当前 event_id 会被排除，避免当前消息重复进入 prompt。
    """

    if not settings.enabled:
        return [], {
            "short_context_enabled": False,
            "short_context_count": 0,
            "short_context_input_ids": [],
        }

    limit = max(0, settings.limit)
    max_chars = max(0, settings.max_chars)
    window_minutes = max(0, settings.window_minutes)
    if limit == 0 or max_chars == 0:
        return [], {
            "short_context_enabled": True,
            "short_context_count": 0,
            "short_context_input_ids": [],
            "short_context_limit": limit,
            "short_context_max_chars": max_chars,
            "short_context_window_minutes": window_minutes,
        }

    threshold = event.timestamp - timedelta(minutes=window_minutes) if window_minutes else None
    conditions = [
        SceneRecord.platform == str(event.platform),
        SceneRecord.scene_type == str(event.scene_type),
        SceneRecord.scene_id == event.scene_id,
        InputRecord.event_id != event.event_id,
        InputRecord.content_type == "text",
        InputRecord.content_text.is_not(None),
    ]
    if threshold is not None:
        conditions.append(InputRecord.created_at >= threshold)

    rows = session.execute(
        select(InputRecord, UserRecord, OutputRecord)
        .join(UserRecord, InputRecord.user_id == UserRecord.id)
        .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
        .outerjoin(OutputRecord, OutputRecord.input_id == InputRecord.id)
        .where(*conditions)
        .order_by(InputRecord.created_at.desc(), InputRecord.id.desc())
        .limit(limit * 3)
    ).all()

    selected: list[ShortContextItem] = []
    used_chars = 0
    seen_input_ids: set[int] = set()
    for input_record, user, output in rows:
        if input_record.id in seen_input_ids:
            continue
        user_text = normalize_context_text(input_record.content_text)
        if not user_text:
            continue
        kaka_text = normalize_context_text(output.content_text) if output is not None else None
        item_chars = len(user_text) + len(kaka_text or "")
        if selected and used_chars + item_chars > max_chars:
            break
        if item_chars > max_chars:
            user_text, kaka_text = trim_context_pair(user_text, kaka_text, max_chars)
            item_chars = len(user_text) + len(kaka_text or "")
        selected.append(
            ShortContextItem(
                input_id=input_record.id,
                user_id=user.platform_user_id,
                display_name=user.display_name or user.platform_user_id,
                user_text=user_text,
                kaka_text=kaka_text,
                created_at=input_record.created_at,
            )
        )
        seen_input_ids.add(input_record.id)
        used_chars += item_chars
        if len(selected) >= limit:
            break

    selected.reverse()
    return selected, {
        "short_context_enabled": True,
        "short_context_count": len(selected),
        "short_context_input_ids": [item.input_id for item in selected],
        "short_context_limit": limit,
        "short_context_max_chars": max_chars,
        "short_context_window_minutes": window_minutes,
    }


def format_short_context(items: list[ShortContextItem]) -> str:
    lines: list[str] = []
    for item in items:
        lines.append(f"{item.display_name}：{item.user_text}")
        if item.kaka_text:
            lines.append(f"卡咔：{item.kaka_text}")
    return "\n".join(lines)


def normalize_context_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def trim_context_pair(user_text: str, kaka_text: str | None, max_chars: int) -> tuple[str, str | None]:
    if max_chars <= 0:
        return "", None
    if kaka_text:
        user_budget = max(1, max_chars // 2)
        kaka_budget = max(0, max_chars - user_budget)
        return trim_text(user_text, user_budget), trim_text(kaka_text, kaka_budget) or None
    return trim_text(user_text, max_chars), None


def trim_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(value) <= max_chars:
        return value
    if max_chars <= 1:
        return value[:max_chars]
    return value[: max_chars - 1].rstrip() + "…"
