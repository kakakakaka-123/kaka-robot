from datetime import datetime, timezone
from pathlib import Path
import importlib.util
import sys

from kaka_core.storage.models import Base, MemoryRecord, SceneRecord, UserRecord, utc_now
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "search_memories.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("search_memories", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_build_filters_supports_group_context():
    module = load_script_module()

    args = module.parse_args_from_list(
        [
            "--user",
            "10001",
            "--group",
            "20002",
            "--text",
            "我现在要做卡咔的记忆检索",
            "--limit",
            "8",
            "--pool-size",
            "50",
        ]
    )
    filters = module.build_filters(args)

    assert filters.user_id == "10001"
    assert filters.query_text == "我现在要做卡咔的记忆检索"
    assert filters.target_scene_type == "group"
    assert filters.target_scene_id == "20002"
    assert filters.limit == 8
    assert filters.pool_size == 50


def test_pycharm_simple_config_builds_search_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_USER_ID", "10001")
    monkeypatch.setattr(module, "PYCHARM_TEXT", "我现在要做卡咔的记忆检索")
    monkeypatch.setattr(module, "PYCHARM_GROUP_ID", "20002")
    monkeypatch.setattr(module, "PYCHARM_PRIVATE", False)
    monkeypatch.setattr(module, "PYCHARM_LIMIT", 8)
    monkeypatch.setattr(module, "PYCHARM_POOL_SIZE", 50)
    monkeypatch.setattr(module, "PYCHARM_MIN_SCORE", 0.5)
    monkeypatch.setattr(module, "PYCHARM_MEMORY_TYPE", "user_fact")

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.user_id == "10001"
    assert filters.query_text == "我现在要做卡咔的记忆检索"
    assert filters.target_scene_type == "group"
    assert filters.target_scene_id == "20002"
    assert filters.limit == 8
    assert filters.pool_size == 50
    assert filters.min_score == 0.5
    assert filters.memory_type == "user_fact"


def test_search_returns_only_active_current_user_and_relevant_general_memories():
    module = load_script_module()
    session_factory = create_session_factory()

    with session_factory() as session:
        user = seed_user(session, "10001")
        other_user = seed_user(session, "10002")
        scene = seed_scene(session, "group", "20002")
        seed_memory(
            session,
            user,
            scene,
            "用户正在开发卡咔 的长期记忆检索。",
            memory_type="user_fact",
            confidence=0.8,
        )
        seed_memory(
            session,
            user,
            scene,
            "用户喜欢直接、务实的回答。",
            memory_type="stable_preference",
            confidence=0.9,
        )
        seed_memory(
            session,
            user,
            scene,
            "用户喜欢喝咖啡。",
            memory_type="user_fact",
            confidence=0.95,
        )
        seed_memory(
            session,
            user,
            scene,
            "用户正在开发旧版记忆系统。",
            memory_type="user_fact",
            confidence=0.9,
            status="archived",
        )
        seed_memory(
            session,
            other_user,
            scene,
            "用户正在开发卡咔 的长期记忆检索。",
            memory_type="user_fact",
            confidence=0.9,
        )
        session.commit()

        filters = module.SearchFilters(
            platform="qq",
            user_id="10001",
            query_text="我现在要继续做卡咔记忆检索",
            limit=5,
            target_scene_type="group",
            target_scene_id="20002",
        )
        user = module.load_user(session, filters)
        rows = module.load_memory_pool(session, filters, user)
        results = module.rank_memories(rows, filters)

    result_texts = [result.memory.memory_text for result in results]
    assert result_texts[0] == "用户正在开发卡咔 的长期记忆检索。"
    assert "用户喜欢直接、务实的回答。" in result_texts
    assert "用户喜欢喝咖啡。" not in result_texts
    assert "用户正在开发旧版记忆系统。" not in result_texts
    assert any("关键词命中" in reason for reason in results[0].reasons)


def test_same_scene_memory_ranks_higher_when_text_relevance_is_equal():
    module = load_script_module()
    session_factory = create_session_factory()

    with session_factory() as session:
        user = seed_user(session, "10001")
        same_scene = seed_scene(session, "group", "20002")
        other_scene = seed_scene(session, "group", "30003")
        seed_memory(
            session,
            user,
            other_scene,
            "用户在卡咔项目中测试记忆检索。",
            confidence=0.8,
        )
        seed_memory(
            session,
            user,
            same_scene,
            "用户在卡咔项目中测试记忆检索。",
            confidence=0.8,
        )
        session.commit()

        filters = module.SearchFilters(
            platform="qq",
            user_id="10001",
            query_text="卡咔记忆检索",
            limit=2,
            target_scene_type="group",
            target_scene_id="20002",
        )
        user = module.load_user(session, filters)
        rows = module.load_memory_pool(session, filters, user)
        results = module.rank_memories(rows, filters)

    assert results[0].scene is not None
    assert results[0].scene.scene_id == "20002"
    assert any("同场景" in reason for reason in results[0].reasons)


def create_session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def seed_user(session, platform_user_id: str) -> UserRecord:
    user = UserRecord(
        platform="qq",
        platform_user_id=platform_user_id,
        display_name=f"用户{platform_user_id}",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(user)
    session.flush()
    return user


def seed_scene(session, scene_type: str, scene_id: str) -> SceneRecord:
    scene = SceneRecord(
        platform="qq",
        scene_type=scene_type,
        scene_id=scene_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(scene)
    session.flush()
    return scene


def seed_memory(
    session,
    user: UserRecord,
    scene: SceneRecord,
    memory_text: str,
    *,
    memory_type: str = "user_fact",
    confidence: float = 0.8,
    status: str = "active",
) -> MemoryRecord:
    memory = MemoryRecord(
        user_id=user.id,
        scene_id=scene.id,
        memory_text=memory_text,
        normalized_text=memory_text.rstrip("。"),
        memory_type=memory_type,
        confidence=confidence,
        source_text=memory_text,
        source="candidate",
        status=status,
        merge_reason="测试记忆",
        created_at=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
    )
    session.add(memory)
    session.flush()
    return memory
