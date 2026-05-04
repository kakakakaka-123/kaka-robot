from pathlib import Path
import importlib.util
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from kaka_core.storage.models import (
    Base,
    InputRecord,
    MemoryCandidateRecord,
    MemoryRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "merge_memory_candidates.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("merge_memory_candidates", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_filters_preview_by_default():
    module = load_script_module()

    args = module.parse_args_from_list(["--limit", "5", "--type", "user_fact", "--ids", "3,4"])
    filters = module.build_filters(args)

    assert filters.limit == 5
    assert filters.candidate_ids == (3, 4)
    assert filters.status == "pending"
    assert filters.memory_type == "user_fact"
    assert filters.apply is False


def test_pycharm_simple_config_builds_candidate_id_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_CANDIDATE_IDS", "7,8")
    monkeypatch.setattr(module, "PYCHARM_LIMIT", 30)
    monkeypatch.setattr(module, "PYCHARM_MEMORY_TYPE", "user_fact")
    monkeypatch.setattr(module, "PYCHARM_MIN_CONFIDENCE", 0.6)
    monkeypatch.setattr(module, "PYCHARM_APPLY", True)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.candidate_ids == (7, 8)
    assert filters.limit == 30
    assert filters.memory_type == "user_fact"
    assert filters.min_confidence == 0.6
    assert filters.apply is True


def test_load_candidates_can_filter_by_candidate_ids():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        first = seed_candidate(session, "用户是物联网工程专业学生。", event_id="input-1")
        second = seed_candidate(session, "用户正在开发卡咔。", event_id="input-2")
        filters = module.MergeFilters(limit=20, candidate_ids=(second.id,))
        rows = module.load_candidates(session, filters)

    assert [row.id for row in rows] == [second.id]
    assert first.id != second.id


def test_apply_merges_candidate_into_memory():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        candidate = seed_candidate(session, "用户是物联网工程专业学生。")
        decisions = module.build_merge_decisions(session, [candidate])
        stats = module.apply_decisions(session, decisions)
        session.commit()

    with session_factory() as session:
        memory = session.scalar(select(MemoryRecord))
        candidate = session.scalar(select(MemoryCandidateRecord))

    assert stats.inserted == 1
    assert stats.duplicates == 0
    assert memory is not None
    assert memory.memory_text == "用户是物联网工程专业学生。"
    assert memory.normalized_text == "用户是物联网工程专业学生"
    assert memory.status == "active"
    assert candidate is not None
    assert candidate.status == "approved"


def test_duplicate_candidate_is_marked_without_new_memory():
    module = load_script_module()
    session_factory = create_session_factory()
    with session_factory() as session:
        first = seed_candidate(session, "用户是物联网工程专业学生。", event_id="input-1")
        second = seed_candidate(session, "用户是物联网工程专业学生。", event_id="input-2")
        decisions = module.build_merge_decisions(session, [first, second])
        stats = module.apply_decisions(session, decisions)
        session.commit()

    with session_factory() as session:
        memories = session.scalars(select(MemoryRecord)).all()
        candidates = session.scalars(
            select(MemoryCandidateRecord).order_by(MemoryCandidateRecord.id)
        ).all()

    assert stats.inserted == 1
    assert stats.duplicates == 1
    assert len(memories) == 1
    assert [candidate.status for candidate in candidates] == ["approved", "merged_duplicate"]


def create_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_candidate(
    session,
    memory_text: str,
    *,
    event_id: str = "input-1",
) -> MemoryCandidateRecord:
    user = session.scalar(select(UserRecord).where(UserRecord.platform_user_id == "10001"))
    if user is None:
        user = UserRecord(
            platform="qq",
            platform_user_id="10001",
            display_name="测试用户",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(user)
        session.flush()

    scene = session.scalar(select(SceneRecord).where(SceneRecord.scene_id == "20002"))
    if scene is None:
        scene = SceneRecord(
            platform="qq",
            scene_type="group",
            scene_id="20002",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(scene)
        session.flush()

    input_record = InputRecord(
        event_id=event_id,
        user=user,
        scene=scene,
        content_type="text",
        content_text="我是物联网工程专业",
        raw_event={},
        extra_metadata={},
        analysis_status="analyzed",
        created_at=utc_now(),
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
        reason="明确身份事实",
        analysis_model="test-model",
        analysis_prompt_version="test-prompt",
        status="pending",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(candidate)
    session.flush()
    return candidate
