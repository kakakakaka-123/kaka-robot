from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from kaka_core.config.settings import get_settings
from kaka_core.memory import merge as memory_merge
from kaka_core.memory.search import MemorySearchFilters, format_scene_type, search_user_memories
from kaka_core.storage.models import (
    InputRecord,
    MemoryCandidateRecord,
    MemoryRecord,
    OutputRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
VALID_MEMORY_STATUSES = {"active", "archived"}
VALID_INPUT_STATUSES = {"not_analyzed", "analyzed", "skipped"}
VALID_CANDIDATE_STATUSES = {"pending", "approved", "rejected", "merged_duplicate"}


@dataclass(frozen=True)
class ListFilters:
    limit: int = 50
    ids: tuple[int, ...] = ()
    status: str | None = None
    memory_type: str | None = None
    group_id: str | None = None
    user_id: str | None = None
    target_date: date | None = None
    scene_type: str | None = None
    reply_state: str | None = None
    output_origin: str | None = None
    output_reason: str | None = None


def get_admin_summary(session: Session) -> dict[str, Any]:
    settings = get_settings()
    candidate_counts = count_by_field(session, MemoryCandidateRecord.status)
    memory_counts = count_by_field(session, MemoryRecord.status)
    input_counts = count_by_field(session, InputRecord.analysis_status)

    return {
        "counts": {
            "users": count_rows(session, UserRecord),
            "scenes": count_rows(session, SceneRecord),
            "inputs": count_rows(session, InputRecord),
            "outputs": count_rows(session, OutputRecord),
            "memory_candidates": count_rows(session, MemoryCandidateRecord),
            "memories": count_rows(session, MemoryRecord),
            "not_analyzed_inputs": input_counts.get("not_analyzed", 0),
            "pending_candidates": candidate_counts.get("pending", 0),
            "active_memories": memory_counts.get("active", 0),
            "archived_memories": memory_counts.get("archived", 0),
        },
        "candidate_statuses": candidate_counts,
        "memory_statuses": memory_counts,
        "input_statuses": input_counts,
        "settings": {
            "database_url": redact_connection_url(settings.database.url),
            "llm_enabled": settings.llm.enabled,
            "llm_can_call_remote": settings.llm.can_call_remote,
            "llm_base_url": settings.llm.base_url,
            "llm_chat_model": settings.llm.chat_model,
            "memory_auto_analysis_enabled": settings.memory_analysis.enabled,
            "memory_auto_analysis_trigger_count": settings.memory_analysis.trigger_count,
            "memory_auto_review_enabled": settings.memory_review.enabled,
            "memory_auto_review_trigger_count": settings.memory_review.trigger_count,
            "memory_reply_injection_enabled": settings.memory_reply.enabled,
            "memory_reply_limit": settings.memory_reply.limit,
            "memory_reply_min_score": settings.memory_reply.min_score,
            "admin_local_only": settings.admin.local_only,
            "admin_api_token_configured": bool(settings.admin.api_token),
        },
        "server_time": format_local_time(utc_now()),
    }


def redact_connection_url(value: str) -> str:
    """隐藏数据库连接串里的密码后再返回给管理台。"""

    try:
        return make_url(value).render_as_string(hide_password=True)
    except Exception:  # noqa: BLE001
        return value


def count_rows(session: Session, model: type) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def count_by_field(session: Session, field: Any) -> dict[str, int]:
    rows = session.execute(select(field, func.count()).group_by(field)).all()
    return {str(key): int(value) for key, value in rows}


def list_conversations(session: Session, filters: ListFilters) -> dict[str, Any]:
    statement = (
        select(InputRecord, UserRecord, SceneRecord, OutputRecord)
        .join(UserRecord, InputRecord.user_id == UserRecord.id)
        .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
        .outerjoin(OutputRecord, OutputRecord.input_id == InputRecord.id)
    )
    statement = apply_common_input_filters(statement, filters)

    if filters.reply_state == "replied":
        statement = statement.where(OutputRecord.should_reply.is_(True))
    elif filters.reply_state == "no_reply":
        statement = statement.where(OutputRecord.id.is_not(None), OutputRecord.should_reply.is_(False))
    elif filters.reply_state == "observed":
        statement = statement.where(OutputRecord.id.is_(None))

    if filters.output_origin:
        statement = statement.where(OutputRecord.output_origin == filters.output_origin)
    if filters.output_reason:
        statement = statement.where(OutputRecord.output_reason == filters.output_reason)

    statement = statement.order_by(InputRecord.created_at.desc()).limit(filters.limit)
    rows = session.execute(statement).all()
    return {"items": [serialize_conversation(*row) for row in rows], "limit": filters.limit}


def list_inputs(session: Session, filters: ListFilters) -> dict[str, Any]:
    statement = (
        select(InputRecord, UserRecord, SceneRecord)
        .join(UserRecord, InputRecord.user_id == UserRecord.id)
        .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
    )
    statement = apply_common_input_filters(statement, filters)
    if filters.status and filters.status != "all":
        statement = statement.where(InputRecord.analysis_status == filters.status)
    statement = statement.order_by(InputRecord.created_at.desc()).limit(filters.limit)
    rows = session.execute(statement).all()
    return {"items": [serialize_input(*row) for row in rows], "limit": filters.limit}


def preview_input_analysis(session: Session, filters: ListFilters) -> dict[str, Any]:
    analyze_inputs = load_script_module("analyze_inputs.py", "kaka_admin_analyze_inputs")
    statement = (
        select(InputRecord, UserRecord, SceneRecord)
        .join(UserRecord, InputRecord.user_id == UserRecord.id)
        .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
    )
    statement = apply_common_input_filters(statement, filters)
    if filters.status and filters.status != "all":
        statement = statement.where(InputRecord.analysis_status == filters.status)
    statement = statement.order_by(InputRecord.created_at.desc()).limit(filters.limit)
    rows = session.execute(statement).all()

    items = []
    for input_record, user, scene in rows:
        row = serialize_input(input_record, user, scene)
        result = analyze_inputs.classify_input_text(input_record.content_text)
        items.append(
            {
                **row,
                "analysis_label": result.label,
                "analysis_reason": result.reason,
                "can_mark_skipped": bool(getattr(result, "can_mark_skipped", False)),
            }
        )
    return {"items": items, "limit": filters.limit}


def mark_inputs_skipped(session: Session, input_ids: tuple[int, ...]) -> dict[str, Any]:
    if not input_ids:
        return {"updated": 0, "skipped": 0}
    analyze_inputs = load_script_module("analyze_inputs.py", "kaka_admin_analyze_inputs")
    inputs = session.scalars(select(InputRecord).where(InputRecord.id.in_(input_ids))).all()
    updated = 0
    skipped = 0
    for input_record in inputs:
        result = analyze_inputs.classify_input_text(input_record.content_text)
        if not getattr(result, "can_mark_skipped", False):
            skipped += 1
            continue
        input_record.analysis_status = "skipped"
        updated += 1
    return {"updated": updated, "skipped": skipped}


def set_input_status(session: Session, input_ids: tuple[int, ...], status: str) -> dict[str, Any]:
    if status not in VALID_INPUT_STATUSES:
        raise ValueError(f"unsupported input status: {status}")
    inputs = session.scalars(select(InputRecord).where(InputRecord.id.in_(input_ids))).all()
    updated = 0
    for input_record in inputs:
        if input_record.analysis_status == status:
            continue
        input_record.analysis_status = status
        updated += 1
    return {"updated": updated, "matched": len(inputs), "status": status}


def list_candidates(session: Session, filters: ListFilters) -> dict[str, Any]:
    statement = (
        select(MemoryCandidateRecord, InputRecord, UserRecord, SceneRecord)
        .join(InputRecord, MemoryCandidateRecord.source_input_id == InputRecord.id)
        .join(UserRecord, MemoryCandidateRecord.source_user_id == UserRecord.id)
        .join(SceneRecord, MemoryCandidateRecord.source_scene_id == SceneRecord.id)
    )
    if filters.ids:
        statement = statement.where(MemoryCandidateRecord.id.in_(filters.ids))
    if filters.status and filters.status != "all":
        statement = statement.where(MemoryCandidateRecord.status == filters.status)
    if filters.memory_type:
        statement = statement.where(MemoryCandidateRecord.memory_type == filters.memory_type)
    if filters.user_id:
        statement = statement.where(UserRecord.platform_user_id == filters.user_id)
    if filters.group_id:
        statement = statement.where(SceneRecord.scene_type == "group", SceneRecord.scene_id == filters.group_id)
    if filters.scene_type:
        statement = statement.where(SceneRecord.scene_type == filters.scene_type)
    if filters.target_date:
        start_utc, end_utc = local_date_to_utc_range(filters.target_date)
        statement = statement.where(
            MemoryCandidateRecord.created_at >= start_utc,
            MemoryCandidateRecord.created_at < end_utc,
        )
    statement = statement.order_by(MemoryCandidateRecord.created_at.desc()).limit(filters.limit)
    rows = session.execute(statement).all()
    return {"items": [serialize_candidate(*row) for row in rows], "limit": filters.limit}


def merge_candidates(
    session: Session,
    candidate_ids: tuple[int, ...],
    *,
    apply: bool,
    limit: int = 50,
) -> dict[str, Any]:
    filters = memory_merge.MergeFilters(
        limit=limit,
        candidate_ids=candidate_ids,
        apply=apply,
    )
    candidates = memory_merge.load_candidates(session, filters)
    decisions = memory_merge.build_merge_decisions(session, candidates)
    stats = memory_merge.apply_decisions(session, decisions) if apply else memory_merge.MergeStats()
    return {
        "mode": "apply" if apply else "preview",
        "candidate_count": len(candidates),
        "plan": {
            "insert": sum(1 for item in decisions if item.action == "insert"),
            "duplicate": sum(1 for item in decisions if item.action == "duplicate"),
            "skip": sum(1 for item in decisions if item.action == "skip"),
        },
        "stats": {
            "inserted": stats.inserted,
            "duplicates": stats.duplicates,
            "skipped": stats.skipped,
        },
        "items": [serialize_merge_decision(item) for item in decisions],
    }


def set_candidate_status(session: Session, candidate_ids: tuple[int, ...], status: str) -> dict[str, Any]:
    if status not in VALID_CANDIDATE_STATUSES:
        raise ValueError(f"unsupported candidate status: {status}")
    candidates = session.scalars(select(MemoryCandidateRecord).where(MemoryCandidateRecord.id.in_(candidate_ids))).all()
    updated = 0
    for candidate in candidates:
        if candidate.status == status:
            continue
        candidate.status = status
        candidate.updated_at = utc_now()
        updated += 1
    return {"updated": updated, "matched": len(candidates), "status": status}


def list_memories(session: Session, filters: ListFilters) -> dict[str, Any]:
    statement = (
        select(MemoryRecord, UserRecord, SceneRecord, MemoryCandidateRecord)
        .join(UserRecord, MemoryRecord.user_id == UserRecord.id)
        .outerjoin(SceneRecord, MemoryRecord.scene_id == SceneRecord.id)
        .outerjoin(MemoryCandidateRecord, MemoryRecord.source_candidate_id == MemoryCandidateRecord.id)
    )
    if filters.ids:
        statement = statement.where(MemoryRecord.id.in_(filters.ids))
    if filters.status and filters.status != "all":
        statement = statement.where(MemoryRecord.status == filters.status)
    if filters.memory_type:
        statement = statement.where(MemoryRecord.memory_type == filters.memory_type)
    if filters.user_id:
        statement = statement.where(UserRecord.platform_user_id == filters.user_id)
    if filters.group_id:
        statement = statement.where(SceneRecord.scene_type == "group", SceneRecord.scene_id == filters.group_id)
    if filters.scene_type:
        statement = statement.where(SceneRecord.scene_type == filters.scene_type)
    if filters.target_date:
        start_utc, end_utc = local_date_to_utc_range(filters.target_date)
        statement = statement.where(
            MemoryRecord.created_at >= start_utc,
            MemoryRecord.created_at < end_utc,
        )
    statement = statement.order_by(MemoryRecord.updated_at.desc(), MemoryRecord.created_at.desc()).limit(filters.limit)
    rows = session.execute(statement).all()
    return {"items": [serialize_memory(*row) for row in rows], "limit": filters.limit}


def set_memory_status(session: Session, memory_ids: tuple[int, ...], status: str) -> dict[str, Any]:
    if status not in VALID_MEMORY_STATUSES:
        raise ValueError(f"unsupported memory status: {status}")
    memories = session.scalars(select(MemoryRecord).where(MemoryRecord.id.in_(memory_ids))).all()
    updated = 0
    for memory in memories:
        if memory.status == status:
            continue
        memory.status = status
        memory.updated_at = utc_now()
        updated += 1
    return {"updated": updated, "matched": len(memories), "status": status}


def delete_memories(session: Session, memory_ids: tuple[int, ...]) -> dict[str, Any]:
    memories = session.scalars(select(MemoryRecord).where(MemoryRecord.id.in_(memory_ids))).all()
    for memory in memories:
        session.delete(memory)
    return {"deleted": len(memories)}


def search_memories(
    session: Session,
    *,
    user_id: str,
    text: str,
    group_id: str | None = None,
    private: bool = False,
    limit: int = 5,
    pool_size: int = 300,
    min_score: float = 1.0,
    memory_type: str | None = None,
) -> dict[str, Any]:
    target_scene_type = None
    target_scene_id = None
    if group_id:
        target_scene_type = "group"
        target_scene_id = group_id
    elif private:
        target_scene_type = "private"
        target_scene_id = user_id
    filters = MemorySearchFilters(
        platform="qq",
        user_id=user_id,
        query_text=text,
        limit=limit,
        pool_size=pool_size,
        min_score=min_score,
        memory_type=memory_type,
        target_scene_type=target_scene_type,
        target_scene_id=target_scene_id,
    )
    results = search_user_memories(session, filters)
    return {
        "items": [
            {
                "memory": serialize_memory_record(result.memory),
                "scene": serialize_scene(result.scene),
                "score": result.score,
                "matched_terms": list(result.matched_terms),
                "reasons": list(result.reasons),
            }
            for result in results
        ],
        "query": {
            "user_id": user_id,
            "text": text,
            "group_id": group_id,
            "private": private,
            "limit": limit,
            "pool_size": pool_size,
            "min_score": min_score,
            "memory_type": memory_type,
        },
    }


def apply_common_input_filters(statement: Any, filters: ListFilters) -> Any:
    if filters.ids:
        statement = statement.where(InputRecord.id.in_(filters.ids))
    if filters.user_id:
        statement = statement.where(UserRecord.platform_user_id == filters.user_id)
    if filters.group_id:
        statement = statement.where(SceneRecord.scene_type == "group", SceneRecord.scene_id == filters.group_id)
    if filters.scene_type:
        statement = statement.where(SceneRecord.scene_type == filters.scene_type)
    if filters.target_date:
        start_utc, end_utc = local_date_to_utc_range(filters.target_date)
        statement = statement.where(InputRecord.created_at >= start_utc, InputRecord.created_at < end_utc)
    return statement


def serialize_conversation(
    input_record: InputRecord,
    user: UserRecord,
    scene: SceneRecord,
    output: OutputRecord | None,
) -> dict[str, Any]:
    return {
        **serialize_input(input_record, user, scene),
        "output": serialize_output(output),
        "reply_state": format_reply_state(output),
    }


def serialize_input(input_record: InputRecord, user: UserRecord, scene: SceneRecord) -> dict[str, Any]:
    return {
        "id": input_record.id,
        "event_id": input_record.event_id,
        "content_type": input_record.content_type,
        "content_text": input_record.content_text or "",
        "analysis_status": input_record.analysis_status,
        "created_at": format_local_time(input_record.created_at),
        "created_at_iso": format_iso(input_record.created_at),
        "user": serialize_user(user),
        "scene": serialize_scene(scene),
    }


def serialize_candidate(
    candidate: MemoryCandidateRecord,
    input_record: InputRecord,
    user: UserRecord,
    scene: SceneRecord,
) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "source_input_id": input_record.id,
        "candidate_memory": candidate.candidate_memory,
        "source_text": candidate.source_text,
        "memory_type": candidate.memory_type,
        "confidence": candidate.confidence,
        "reason": candidate.reason,
        "status": candidate.status,
        "analysis_model": candidate.analysis_model,
        "analysis_prompt_version": candidate.analysis_prompt_version,
        "created_at": format_local_time(candidate.created_at),
        "updated_at": format_local_time(candidate.updated_at),
        "user": serialize_user(user),
        "scene": serialize_scene(scene),
    }


def serialize_memory(
    memory: MemoryRecord,
    user: UserRecord,
    scene: SceneRecord | None,
    candidate: MemoryCandidateRecord | None,
) -> dict[str, Any]:
    return {
        **serialize_memory_record(memory),
        "user": serialize_user(user),
        "scene": serialize_scene(scene),
        "candidate_id": candidate.id if candidate is not None else memory.source_candidate_id,
    }


def serialize_memory_record(memory: MemoryRecord) -> dict[str, Any]:
    return {
        "id": memory.id,
        "source_candidate_id": memory.source_candidate_id,
        "memory_text": memory.memory_text,
        "normalized_text": memory.normalized_text,
        "memory_type": memory.memory_type,
        "confidence": memory.confidence,
        "source_text": memory.source_text or "",
        "source": memory.source,
        "status": memory.status,
        "merge_reason": memory.merge_reason or "",
        "created_at": format_local_time(memory.created_at),
        "updated_at": format_local_time(memory.updated_at),
    }


def serialize_merge_decision(decision: Any) -> dict[str, Any]:
    return {
        "candidate_id": decision.candidate.id,
        "action": decision.action,
        "normalized_text": decision.normalized_text,
        "reason": decision.reason,
        "duplicate_memory_id": decision.duplicate_memory_id,
        "candidate_memory": decision.candidate.candidate_memory,
        "memory_type": decision.candidate.memory_type,
        "confidence": decision.candidate.confidence,
    }


def serialize_user(user: UserRecord | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "platform": user.platform,
        "platform_user_id": user.platform_user_id,
        "display_name": user.display_name or user.platform_user_id,
    }


def serialize_scene(scene: SceneRecord | None) -> dict[str, Any] | None:
    if scene is None:
        return None
    return {
        "id": scene.id,
        "platform": scene.platform,
        "scene_type": scene.scene_type,
        "scene_type_label": format_scene_type(scene.scene_type),
        "scene_id": scene.scene_id,
    }


def serialize_output(output: OutputRecord | None) -> dict[str, Any] | None:
    if output is None:
        return None
    return {
        "id": output.id,
        "output_id": output.output_id,
        "output_origin": output.output_origin,
        "output_reason": output.output_reason,
        "should_reply": output.should_reply,
        "no_reply_reason": output.no_reply_reason,
        "content_text": output.content_text or "",
        "created_at": format_local_time(output.created_at),
    }


def format_reply_state(output: OutputRecord | None) -> str:
    if output is None:
        return "observed"
    if output.should_reply:
        return "replied"
    return "no_reply"


def parse_ids(value: str | None) -> tuple[int, ...]:
    if value is None:
        return ()
    ids: list[int] = []
    for piece in value.split(","):
        text = piece.strip()
        if not text:
            continue
        number = int(text)
        if number > 0 and number not in ids:
            ids.append(number)
    return tuple(ids)


def normalize_text(value: str | None) -> str | None:
    text = str(value or "").strip()
    return text or None


def parse_date(value: str | None) -> date | None:
    text = normalize_text(value)
    if text is None:
        return None
    return date.fromisoformat(text)


def clamp_limit(value: int, *, default: int = 50, maximum: int = 200) -> int:
    if value <= 0:
        return default
    return min(value, maximum)


def local_date_to_utc_range(value: date) -> tuple[datetime, datetime]:
    start_local = datetime.combine(value, time.min, tzinfo=LOCAL_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def format_local_time(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def format_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def load_script_module(filename: str, module_name: str) -> ModuleType:
    repo_root = Path(__file__).resolve().parents[5]
    script_path = repo_root / "services" / "kaka-core" / "scripts" / filename
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load script: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
