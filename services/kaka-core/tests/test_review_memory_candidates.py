from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import json
import sys

from kaka_core.storage.models import (
    Base,
    InputRecord,
    MemoryCandidateRecord,
    MemoryRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "review_memory_candidates.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("review_memory_candidates", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_filters_supports_common_options():
    module = load_script_module()

    args = module.parse_args_from_list(
        [
            "--limit",
            "5",
            "--batch-size",
            "3",
            "--type",
            "user_fact",
            "--group",
            "20002",
            "--user",
            "10001",
            "--min-confidence",
            "0.6",
            "--ids",
            "7,8",
            "--apply",
        ]
    )
    filters = module.build_filters(args)

    assert filters.limit == 5
    assert filters.batch_size == 3
    assert filters.candidate_ids == (7, 8)
    assert filters.memory_type == "user_fact"
    assert filters.group_id == "20002"
    assert filters.user_id == "10001"
    assert filters.min_confidence == 0.6
    assert filters.apply is True


def test_pycharm_simple_config_builds_candidate_id_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_CANDIDATE_IDS", "9,10")
    monkeypatch.setattr(module, "PYCHARM_LIMIT", 30)
    monkeypatch.setattr(module, "PYCHARM_BATCH_SIZE", 4)
    monkeypatch.setattr(module, "PYCHARM_MEMORY_TYPE", "stable_preference")
    monkeypatch.setattr(module, "PYCHARM_GROUP_ID", "20002")
    monkeypatch.setattr(module, "PYCHARM_USER_ID", "10001")
    monkeypatch.setattr(module, "PYCHARM_MIN_CONFIDENCE", 0.7)
    monkeypatch.setattr(module, "PYCHARM_APPLY", True)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.candidate_ids == (9, 10)
    assert filters.limit == 30
    assert filters.batch_size == 4
    assert filters.memory_type == "stable_preference"
    assert filters.group_id == "20002"
    assert filters.user_id == "10001"
    assert filters.min_confidence == 0.7
    assert filters.apply is True


def test_review_prompt_requires_third_person_memory_expression():
    module = load_script_module()

    assert "approve 的 memory 必须写成稳定、简洁的第三人称事实" in module.REVIEW_SYSTEM_PROMPT
    assert "不能以“我 / 我的 / 本人”表达" in module.REVIEW_SYSTEM_PROMPT
    assert "该用户希望卡咔先给结论" in module.REVIEW_SYSTEM_PROMPT


def test_review_batch_and_apply_approves_and_rejects_candidates():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        user, scene = seed_user_and_scene(session)
        approved = seed_candidate(session, user, scene, "用户正在开发卡咔 v2。")
        rejected = seed_candidate(session, user, scene, "哈哈哈", event_id="input-2")
        rows = [
            module.CandidateReviewRow(approved, user, scene, ()),
            module.CandidateReviewRow(rejected, user, scene, ()),
        ]
        router = FakeRouter(
            [
                {
                    "id": approved.id,
                    "action": "approve",
                    "type": "user_fact",
                    "confidence": 0.8,
                    "reason": "项目事实",
                    "memory": "用户正在开发卡咔 v2。",
                },
                {
                    "id": rejected.id,
                    "action": "reject",
                    "type": "user_fact",
                    "confidence": 0.2,
                    "reason": "低价值闲聊",
                    "memory": "",
                },
            ]
        )
        decisions, _keys = run_async(module.review_batch(rows, router, set()))
        stats = module.apply_decisions(session, decisions)
        session.commit()

        memory = session.scalar(select(MemoryRecord))
        candidates = session.scalars(
            select(MemoryCandidateRecord).order_by(MemoryCandidateRecord.id)
        ).all()

    assert [decision.action for decision in decisions] == ["approve", "reject"]
    assert stats.approved == 1
    assert stats.rejected == 1
    assert memory is not None
    assert memory.memory_text == "用户正在开发卡咔 v2。"
    assert [candidate.status for candidate in candidates] == ["approved", "rejected"]


def test_review_batch_marks_duplicate_within_same_batch():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        user, scene = seed_user_and_scene(session)
        first = seed_candidate(session, user, scene, "用户喜欢直接回答。")
        second = seed_candidate(
            session,
            user,
            scene,
            "用户喜欢直接回答！",
            event_id="input-2",
        )
        rows = [
            module.CandidateReviewRow(first, user, scene, ()),
            module.CandidateReviewRow(second, user, scene, ()),
        ]
        router = FakeRouter(
            [
                {
                    "id": first.id,
                    "action": "approve",
                    "type": "stable_preference",
                    "confidence": 0.9,
                    "reason": "稳定偏好",
                    "memory": "用户喜欢直接回答。",
                },
                {
                    "id": second.id,
                    "action": "approve",
                    "type": "stable_preference",
                    "confidence": 0.9,
                    "reason": "稳定偏好",
                    "memory": "用户喜欢直接回答！",
                },
            ]
        )
        decisions, _keys = run_async(module.review_batch(rows, router, set()))

    assert [decision.action for decision in decisions] == ["approve", "duplicate"]


def test_review_batch_promotes_clear_first_person_relationship_fact():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        user, scene = seed_user_and_scene(session)
        candidate = seed_candidate(session, user, scene, "他是我导师王老师。")
        rows = [module.CandidateReviewRow(candidate, user, scene, ())]
        router = FakeRouter(
            [
                {
                    "id": candidate.id,
                    "action": "reject",
                    "type": "user_fact",
                    "confidence": 0.2,
                    "reason": "关系信息",
                    "memory": "",
                }
            ]
        )
        decisions, _keys = run_async(module.review_batch(rows, router, set()))

    assert len(decisions) == 1
    assert decisions[0].action == "approve"
    assert decisions[0].memory_type == "relationship_fact"
    assert decisions[0].memory_text == "测试用户的导师是王老师。"


def test_review_batch_normalizes_preference_memory_type():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        user, scene = seed_user_and_scene(session)
        candidate = seed_candidate(session, user, scene, "回复时先给结论。")
        candidate.memory_type = "relationship_fact"
        rows = [module.CandidateReviewRow(candidate, user, scene, ())]
        router = FakeRouter(
            [
                {
                    "id": candidate.id,
                    "action": "approve",
                    "type": "relationship_fact",
                    "confidence": 0.8,
                    "reason": "候选可用",
                    "memory": "测试用户希望回复时先给结论。",
                }
            ]
        )
        decisions, _keys = run_async(module.review_batch(rows, router, set()))
        stats = module.apply_decisions(session, decisions)
        session.commit()

        updated_candidate = session.get(MemoryCandidateRecord, candidate.id)

    assert len(decisions) == 1
    assert decisions[0].action == "approve"
    assert decisions[0].memory_type == "stable_preference"
    assert stats.approved == 1
    assert updated_candidate is not None
    assert updated_candidate.memory_type == "stable_preference"


def run_async(coro):
    import asyncio

    return asyncio.run(coro)


class FakeRouter:
    def __init__(self, data):
        self.data = data

    async def summarize_memory(self, _messages):
        return json.dumps(self.data, ensure_ascii=False)


def create_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_user_and_scene(session):
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
    return user, scene


def seed_candidate(
    session,
    user: UserRecord,
    scene: SceneRecord,
    memory_text: str,
    *,
    event_id: str = "input-1",
) -> MemoryCandidateRecord:
    input_record = InputRecord(
        event_id=event_id,
        user=user,
        scene=scene,
        content_type="text",
        content_text=memory_text,
        raw_event={},
        extra_metadata={},
        analysis_status="analyzed",
        created_at=datetime(2026, 5, 2, 1, 0, tzinfo=timezone.utc),
    )
    session.add(input_record)
    session.flush()
    candidate = MemoryCandidateRecord(
        source_input_id=input_record.id,
        source_user_id=user.id,
        source_scene_id=scene.id,
        source_text=input_record.content_text or "",
        candidate_memory=memory_text,
        memory_type="user_fact",
        confidence=0.8,
        reason="测试候选",
        analysis_model="test-model",
        analysis_prompt_version="test-prompt",
        status="pending",
        created_at=datetime(2026, 5, 2, 1, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 2, 1, 0, tzinfo=timezone.utc),
    )
    session.add(candidate)
    session.flush()
    return candidate
