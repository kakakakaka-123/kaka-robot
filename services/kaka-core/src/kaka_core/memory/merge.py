from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from kaka_core.storage.models import MemoryCandidateRecord, MemoryRecord

MEMORY_STATUS_ACTIVE = "active"
MEMORY_SOURCE_CANDIDATE = "candidate"
CANDIDATE_STATUS_PENDING = "pending"
CANDIDATE_STATUS_APPROVED = "approved"
CANDIDATE_STATUS_DUPLICATE = "merged_duplicate"


@dataclass(frozen=True)
class MergeFilters:
    limit: int
    candidate_ids: tuple[int, ...] = ()
    status: str = CANDIDATE_STATUS_PENDING
    memory_type: str | None = None
    min_confidence: float = 0.0
    apply: bool = False


@dataclass(frozen=True)
class MergeDecision:
    candidate: MemoryCandidateRecord
    action: str
    normalized_text: str
    reason: str
    duplicate_memory_id: int | None = None


@dataclass
class MergeStats:
    inserted: int = 0
    duplicates: int = 0
    skipped: int = 0


def load_candidates(session: Session, filters: MergeFilters) -> list[MemoryCandidateRecord]:
    statement = select(MemoryCandidateRecord).where(MemoryCandidateRecord.status == filters.status)
    if filters.candidate_ids:
        statement = statement.where(MemoryCandidateRecord.id.in_(filters.candidate_ids))
    if filters.memory_type:
        statement = statement.where(MemoryCandidateRecord.memory_type == filters.memory_type)
    if filters.min_confidence > 0:
        statement = statement.where(MemoryCandidateRecord.confidence >= filters.min_confidence)
    statement = statement.order_by(MemoryCandidateRecord.created_at.asc()).limit(filters.limit)
    return list(session.scalars(statement).all())


def build_merge_decisions(
    session: Session,
    candidates: list[MemoryCandidateRecord],
) -> list[MergeDecision]:
    existing_keys = load_existing_memory_keys(session)
    seen_keys: set[tuple[int, str, str]] = set()
    decisions: list[MergeDecision] = []
    for candidate in candidates:
        normalized_text = normalize_memory_text(candidate.candidate_memory)
        if not normalized_text:
            decisions.append(
                MergeDecision(
                    candidate=candidate,
                    action="skip",
                    normalized_text="",
                    reason="候选记忆为空",
                )
            )
            continue

        key = (candidate.source_user_id, candidate.memory_type, normalized_text)
        duplicate_memory_id = existing_keys.get(key)
        if duplicate_memory_id is not None:
            decisions.append(
                MergeDecision(
                    candidate=candidate,
                    action="duplicate",
                    normalized_text=normalized_text,
                    reason="正式记忆中已有相同用户、类型和内容",
                    duplicate_memory_id=duplicate_memory_id,
                )
            )
            continue
        if key in seen_keys:
            decisions.append(
                MergeDecision(
                    candidate=candidate,
                    action="duplicate",
                    normalized_text=normalized_text,
                    reason="本次待合并候选中已有重复内容",
                )
            )
            continue
        seen_keys.add(key)
        decisions.append(
            MergeDecision(
                candidate=candidate,
                action="insert",
                normalized_text=normalized_text,
                reason="可合并为正式记忆",
            )
        )
    return decisions


def load_existing_memory_keys(session: Session) -> dict[tuple[int, str, str], int]:
    rows = session.execute(
        select(
            MemoryRecord.id,
            MemoryRecord.user_id,
            MemoryRecord.memory_type,
            MemoryRecord.normalized_text,
        ).where(MemoryRecord.status == MEMORY_STATUS_ACTIVE)
    ).all()
    return {
        (int(user_id), str(memory_type), str(normalized_text)): int(memory_id)
        for memory_id, user_id, memory_type, normalized_text in rows
    }


def normalize_memory_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[。.!！?？~～…]+$", "", text)
    return text


def apply_decisions(session: Session, decisions: list[MergeDecision]) -> MergeStats:
    stats = MergeStats()
    for decision in decisions:
        candidate = decision.candidate
        if decision.action == "insert":
            session.add(
                MemoryRecord(
                    source_candidate_id=candidate.id,
                    user_id=candidate.source_user_id,
                    scene_id=candidate.source_scene_id,
                    memory_text=candidate.candidate_memory,
                    normalized_text=decision.normalized_text,
                    memory_type=candidate.memory_type,
                    confidence=candidate.confidence,
                    source_text=candidate.source_text,
                    source=MEMORY_SOURCE_CANDIDATE,
                    status=MEMORY_STATUS_ACTIVE,
                    merge_reason=decision.reason,
                )
            )
            candidate.status = CANDIDATE_STATUS_APPROVED
            stats.inserted += 1
        elif decision.action == "duplicate":
            candidate.status = CANDIDATE_STATUS_DUPLICATE
            stats.duplicates += 1
        else:
            stats.skipped += 1
    return stats


def count_actions(decisions: list[MergeDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
    return counts
