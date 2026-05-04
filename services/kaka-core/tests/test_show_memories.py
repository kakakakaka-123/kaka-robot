from datetime import date, datetime, timezone
from pathlib import Path
import importlib.util
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
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "show_memories.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("show_memories", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_filters_supports_all_status_source_and_date():
    module = load_script_module()

    args = module.parse_args_from_list(
        [
            "--ids",
            "7,8",
            "--status",
            "all",
            "--type",
            "user_fact",
            "--source",
            "candidate",
            "--date",
            "2026-05-01",
            "--limit",
            "5",
        ]
    )
    filters = module.build_filters(args)

    assert filters.memory_ids == (7, 8)
    assert filters.status is None
    assert filters.memory_type == "user_fact"
    assert filters.source == "candidate"
    assert filters.target_date == date(2026, 5, 1)
    assert filters.limit == 5


def test_pycharm_simple_config_builds_memory_id_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_MEMORY_IDS", "7,8")
    monkeypatch.setattr(module, "PYCHARM_LIMIT", 30)
    monkeypatch.setattr(module, "PYCHARM_STATUS", "")
    monkeypatch.setattr(module, "PYCHARM_MEMORY_TYPE", "user_fact")
    monkeypatch.setattr(module, "PYCHARM_SOURCE", "candidate")
    monkeypatch.setattr(module, "PYCHARM_GROUP_ID", "20002")
    monkeypatch.setattr(module, "PYCHARM_USER_ID", "10001")
    monkeypatch.setattr(module, "PYCHARM_DATE", "2026-05-01")
    monkeypatch.setattr(module, "PYCHARM_PRIVATE", False)
    monkeypatch.setattr(module, "PYCHARM_GROUP_CHAT", True)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.memory_ids == (7, 8)
    assert filters.limit == 30
    assert filters.status is None
    assert filters.memory_type == "user_fact"
    assert filters.source == "candidate"
    assert filters.group_id == "20002"
    assert filters.user_id == "10001"
    assert filters.target_date == date(2026, 5, 1)
    assert filters.scene_type == "group"


def test_load_and_format_memories():
    module = load_script_module()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

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

        input_record = InputRecord(
            event_id="input-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="我是物联网工程专业",
            raw_event={},
            extra_metadata={},
            analysis_status="analyzed",
            created_at=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
        )
        session.add(input_record)
        session.flush()

        candidate = MemoryCandidateRecord(
            source_input_id=input_record.id,
            source_user_id=user.id,
            source_scene_id=scene.id,
            source_text=input_record.content_text or "",
            candidate_memory="用户是物联网工程专业学生。",
            memory_type="user_fact",
            confidence=0.8,
            reason="明确身份事实",
            analysis_model="deepseek-v4-flash",
            analysis_prompt_version="test-prompt",
            status="approved",
            created_at=datetime(2026, 5, 1, 2, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 1, 2, 0, tzinfo=timezone.utc),
        )
        session.add(candidate)
        session.flush()

        session.add(
            MemoryRecord(
                source_candidate_id=candidate.id,
                user_id=user.id,
                scene_id=scene.id,
                memory_text="用户是物联网工程专业学生。",
                normalized_text="用户是物联网工程专业学生",
                memory_type="user_fact",
                confidence=0.8,
                source_text=input_record.content_text or "",
                source="candidate",
                status="active",
                merge_reason="可合并为正式记忆",
                created_at=datetime(2026, 5, 1, 3, 0, tzinfo=timezone.utc),
                updated_at=datetime(2026, 5, 1, 3, 0, tzinfo=timezone.utc),
            )
        )
        session.flush()
        target_memory_id = candidate.id
        session.commit()

        filters = module.MemoryFilters(
            limit=10,
            memory_ids=(target_memory_id,),
            status="active",
            memory_type="user_fact",
        )
        rows = module.load_memories(session, filters)
        text = module.format_memory(1, rows[0])

    assert len(rows) == 1
    assert "memory_id=" in text
    assert "candidate_id=" in text
    assert "正式记忆：用户是物联网工程专业学生。" in text
    assert "去重文本：用户是物联网工程专业学生" in text
    assert "合并理由：可合并为正式记忆" in text
