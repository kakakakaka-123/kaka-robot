from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from kaka_core.config.settings import MemoryReviewSettings
from kaka_core.memory import auto_review
from kaka_core.storage.models import (
    Base,
    InputRecord,
    MemoryCandidateRecord,
    MemoryRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_memory_candidates.py"


def load_review_script_module():
    spec = importlib.util.spec_from_file_location(
        "review_memory_candidates_for_auto_test",
        SCRIPT_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_auto_review_seconds_until_next_hour():
    now = datetime(2026, 5, 2, 14, 37, 30, tzinfo=timezone.utc)

    assert auto_review.seconds_until_next_hour(now) == 1350


@pytest.mark.anyio
async def test_auto_review_skips_below_threshold(monkeypatch):
    session_factory = create_session_factory()
    seed_candidates(session_factory, 19)

    monkeypatch.setattr(auto_review, "init_database", lambda: None)
    monkeypatch.setattr(auto_review, "create_session_factory", lambda: session_factory)

    summary = await auto_review.run_auto_review_check(
        MemoryReviewSettings(
            enabled=True,
            trigger_count=20,
            batch_size=10,
            max_runs_per_check=2,
        )
    )

    assert summary.ran is False
    assert summary.checked_count == 19
    assert "未达到触发门槛" in summary.reason


@pytest.mark.anyio
async def test_auto_review_runs_configured_batches(monkeypatch):
    session_factory = create_session_factory()
    seed_candidates(session_factory, 20)
    review_module = load_review_script_module()

    async def fake_review_rows(rows, _router, _batch_size, _existing_keys):
        decisions = []
        for row in rows:
            action = "approve" if row.candidate.id % 2 == 0 else "reject"
            decisions.append(
                review_module.ReviewDecision(
                    candidate=row.candidate,
                    action=action,
                    memory_text=f"该用户测试记忆 {row.candidate.id}。" if action == "approve" else "",
                    memory_type="user_fact",
                    confidence=0.8,
                    reason="测试复核",
                )
            )
        return decisions

    monkeypatch.setattr(review_module, "review_rows", fake_review_rows)
    monkeypatch.setattr(auto_review, "init_database", lambda: None)
    monkeypatch.setattr(auto_review, "create_session_factory", lambda: session_factory)
    monkeypatch.setattr(auto_review, "load_review_candidates_module", lambda: review_module)
    monkeypatch.setattr(auto_review, "LLMRouter", lambda _settings: object())
    monkeypatch.setattr(
        auto_review,
        "get_settings",
        lambda: SimpleNamespace(llm=SimpleNamespace(can_call_remote=True)),
    )

    summary = await auto_review.run_auto_review_check(
        MemoryReviewSettings(
            enabled=True,
            trigger_count=20,
            batch_size=10,
            max_runs_per_check=2,
        )
    )

    with session_factory() as session:
        pending = auto_review.count_pending_candidates(session)
        memory_count = session.scalar(select(func.count()).select_from(MemoryRecord))

    assert summary.ran is True
    assert summary.processed_runs == 2
    assert summary.approved == 10
    assert summary.rejected == 10
    assert pending == 0
    assert memory_count == 10


def create_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_candidates(session_factory, count: int) -> None:
    with session_factory() as session:
        user = UserRecord(
            platform="qq",
            platform_user_id="10001",
            display_name="测试用户",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        scene = SceneRecord(
            platform="qq",
            scene_type="group",
            scene_id="20002",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add_all([user, scene])
        session.flush()
        for index in range(count):
            input_record = InputRecord(
                event_id=f"input-{index}",
                user=user,
                scene=scene,
                content_type="text",
                content_text=f"测试消息 {index}",
                raw_event={},
                extra_metadata={},
                analysis_status="analyzed",
                created_at=utc_now(),
            )
            session.add(input_record)
            session.flush()
            session.add(
                MemoryCandidateRecord(
                    source_input_id=input_record.id,
                    source_user_id=user.id,
                    source_scene_id=scene.id,
                    source_text=input_record.content_text or "",
                    candidate_memory=f"该用户测试记忆 {index}。",
                    memory_type="user_fact",
                    confidence=0.8,
                    reason="测试候选",
                    analysis_model="test-model",
                    analysis_prompt_version="test-prompt",
                    status="pending",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            )
        session.commit()
