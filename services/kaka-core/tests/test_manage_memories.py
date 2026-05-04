from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from kaka_core.storage.models import Base, MemoryRecord, SceneRecord, UserRecord, utc_now


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "manage_memories.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("manage_memories", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_filters_supports_status_and_delete():
    module = load_script_module()

    args = module.parse_args_from_list(
        [
            "--id",
            "1",
            "--id",
            "2",
            "--ids",
            "3,4",
            "--status",
            "archived",
            "--apply",
        ]
    )
    filters = module.build_filters(args)

    assert filters.memory_ids == (1, 2, 3, 4)
    assert filters.target_status == "archived"
    assert filters.delete is False
    assert filters.apply is True


def test_parse_args_reads_real_command_line(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(
        module.sys,
        "argv",
        ["manage_memories.py", "--id", "7", "--status", "archived"],
    )

    args = module.parse_args()
    filters = module.build_filters(args)

    assert filters.memory_ids == (7,)
    assert filters.target_status == "archived"


def test_pycharm_simple_config_builds_archive_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_MEMORY_IDS", "7,8")
    monkeypatch.setattr(module, "PYCHARM_ACTION", "archive")
    monkeypatch.setattr(module, "PYCHARM_APPLY", True)
    monkeypatch.setattr(module, "PYCHARM_CONFIRM_DELETE", False)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.memory_ids == (7, 8)
    assert filters.target_status == "archived"
    assert filters.delete is False
    assert filters.apply is True


def test_pycharm_simple_config_builds_restore_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_MEMORY_IDS", "9")
    monkeypatch.setattr(module, "PYCHARM_ACTION", "restore")
    monkeypatch.setattr(module, "PYCHARM_APPLY", False)
    monkeypatch.setattr(module, "PYCHARM_CONFIRM_DELETE", False)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.memory_ids == (9,)
    assert filters.target_status == "active"
    assert filters.apply is False


def test_pycharm_simple_config_hard_delete_requires_confirmation(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_MEMORY_IDS", "10")
    monkeypatch.setattr(module, "PYCHARM_ACTION", "delete")
    monkeypatch.setattr(module, "PYCHARM_APPLY", True)
    monkeypatch.setattr(module, "PYCHARM_CONFIRM_DELETE", False)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())

    try:
        module.build_filters(args)
    except SystemExit as exc:
        assert "硬删除写入数据库时需要额外传入 --yes" in str(exc)
    else:
        raise AssertionError("硬删除写库时应该要求确认。")


def test_apply_decisions_can_archive_memory():
    module = load_script_module()
    session_factory = create_session_factory()
    memory_id = seed_memory(session_factory, status="active")

    with session_factory() as session:
        memories = module.load_memories(session, (memory_id,))
        filters = SimpleNamespace(
            memory_ids=(memory_id,),
            target_status="archived",
            delete=False,
        )
        decisions = module.build_decisions(memories, filters)
        stats = module.apply_decisions(session, decisions, SimpleNamespace(apply=True, yes=False))
        session.commit()

        memory = session.get(MemoryRecord, memory_id)

    assert stats.updated == 1
    assert memory is not None
    assert memory.status == "archived"


def test_format_summary_shows_preview_plan():
    module = load_script_module()
    decisions = [
        module.ManageDecision(
            memory_id=1,
            action="update",
            before_status="active",
            after_status="archived",
            memory_text="该用户测试记忆。",
            normalized_text="该用户测试记忆",
            memory_type="user_fact",
        ),
        module.ManageDecision(
            memory_id=2,
            action="missing",
            before_status="not_found",
            after_status=None,
            memory_text="",
            normalized_text="",
            memory_type="",
        ),
    ]
    filters = SimpleNamespace(
        memory_ids=(1, 2),
        target_status="archived",
        delete=False,
        apply=False,
    )
    stats = module.ApplyStats()

    text = module.format_summary(filters, decisions, stats)

    assert "正式记忆管理预览" in text
    assert "计划：update=1 / delete=0 / noop=0 / missing=1" in text


def test_apply_decisions_can_hard_delete_memory():
    module = load_script_module()
    session_factory = create_session_factory()
    memory_id = seed_memory(session_factory, status="archived")

    with session_factory() as session:
        memories = module.load_memories(session, (memory_id,))
        filters = SimpleNamespace(
            memory_ids=(memory_id,),
            target_status=None,
            delete=True,
        )
        decisions = module.build_decisions(memories, filters)
        stats = module.apply_decisions(session, decisions, SimpleNamespace(apply=True, yes=True))
        session.commit()

        memory = session.get(MemoryRecord, memory_id)

    assert stats.deleted == 1
    assert memory is None


def create_session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_memory(session_factory, *, status: str) -> int:
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
        memory = MemoryRecord(
            user_id=user.id,
            scene_id=scene.id,
            memory_text="该用户测试记忆。",
            normalized_text="该用户测试记忆",
            memory_type="user_fact",
            confidence=0.8,
            source_text="测试来源",
            source="candidate",
            status=status,
            merge_reason="测试",
            created_at=datetime(2026, 5, 2, 1, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 2, 1, 0, tzinfo=timezone.utc),
        )
        session.add(memory)
        session.commit()
        return memory.id
