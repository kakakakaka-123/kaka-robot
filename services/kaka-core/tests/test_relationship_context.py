from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from kaka_core.config.settings import RelationshipSettings
from kaka_core.relationship.context import load_relationship_context
from kaka_core.storage.database import create_database_engine, init_database
from kaka_core.storage.models import InputRecord, MemoryRecord, SceneRecord, UserRecord, utc_now
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType


def default_relationship_settings(*, owners: frozenset[str] = frozenset()) -> RelationshipSettings:
    return RelationshipSettings(
        owner_user_ids=owners,
        familiar_input_count=100,
        familiar_recent_input_count=30,
        familiar_active_memory_count=8,
        regular_input_count=30,
        regular_recent_input_count=10,
        regular_active_memory_count=3,
        recent_days=7,
    )


def make_event(user_id: str = "10001") -> MessageEvent:
    return MessageEvent(
        event_id=f"relationship-event-{user_id}",
        platform=Platform.QQ,
        scene_type=SceneType.PRIVATE,
        scene_id=user_id,
        user_id=user_id,
        display_name="测试用户",
        content=MessageContent.text_message("你好"),
    )


def test_owner_is_recognized_without_existing_database_user(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'owner.sqlite3'}")
    init_database(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        context = load_relationship_context(
            session,
            make_event("10001"),
            default_relationship_settings(owners=frozenset({"10001"})),
        )

    assert context.level == "owner"
    assert context.is_owner is True
    assert context.input_count == 0


def test_new_user_is_stranger(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'stranger.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, input_count=1)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        context = load_relationship_context(
            session,
            make_event(),
            default_relationship_settings(),
        )

    assert context.level == "stranger"
    assert context.input_count == 1


def test_input_count_thresholds_promote_relationship_level(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'input-threshold.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, input_count=30)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        regular = load_relationship_context(session, make_event(), default_relationship_settings())

    engine = create_database_engine(f"sqlite:///{tmp_path / 'input-familiar.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, input_count=100)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        familiar = load_relationship_context(session, make_event(), default_relationship_settings())

    assert regular.level == "regular"
    assert familiar.level == "familiar"


def test_recent_input_thresholds_promote_relationship_level(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'recent-regular.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, recent_input_count=10, old_input_count=10)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        regular = load_relationship_context(session, make_event(), default_relationship_settings())

    engine = create_database_engine(f"sqlite:///{tmp_path / 'recent-familiar.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, recent_input_count=30, old_input_count=10)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        familiar = load_relationship_context(session, make_event(), default_relationship_settings())

    assert regular.level == "regular"
    assert regular.recent_input_count == 10
    assert familiar.level == "familiar"
    assert familiar.recent_input_count == 30


def test_active_memory_thresholds_promote_relationship_level(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'memory-regular.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, active_memory_count=3)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        regular = load_relationship_context(session, make_event(), default_relationship_settings())

    engine = create_database_engine(f"sqlite:///{tmp_path / 'memory-familiar.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, active_memory_count=8)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as session:
        familiar = load_relationship_context(session, make_event(), default_relationship_settings())

    assert regular.level == "regular"
    assert regular.active_memory_count == 3
    assert familiar.level == "familiar"
    assert familiar.active_memory_count == 8


def seed_relationship_user(
    engine,
    *,
    input_count: int = 0,
    recent_input_count: int = 0,
    old_input_count: int = 0,
    active_memory_count: int = 0,
) -> None:
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    now = utc_now()
    old_time = now - timedelta(days=10)
    with session_factory() as session:
        user = UserRecord(
            platform="qq",
            platform_user_id="10001",
            display_name="测试用户",
            created_at=now,
            updated_at=now,
        )
        scene = SceneRecord(
            platform="qq",
            scene_type="private",
            scene_id="10001",
            created_at=now,
            updated_at=now,
        )
        session.add_all([user, scene])
        session.flush()

        for index in range(recent_input_count):
            session.add(
                InputRecord(
                    event_id=f"recent-input-{index}",
                    user=user,
                    scene=scene,
                    content_type="text",
                    content_text=f"近期消息 {index}",
                    raw_event={},
                    extra_metadata={},
                    analysis_status="not_analyzed",
                    created_at=now,
                )
            )
        total_old_inputs = max(input_count - recent_input_count, 0) + old_input_count
        for index in range(total_old_inputs):
            session.add(
                InputRecord(
                    event_id=f"old-input-{index}",
                    user=user,
                    scene=scene,
                    content_type="text",
                    content_text=f"旧消息 {index}",
                    raw_event={},
                    extra_metadata={},
                    analysis_status="not_analyzed",
                    created_at=old_time,
                )
            )
        for index in range(active_memory_count):
            session.add(
                MemoryRecord(
                    user=user,
                    scene=scene,
                    memory_text=f"用户测试记忆 {index}。",
                    normalized_text=f"用户测试记忆 {index}",
                    memory_type="user_fact",
                    confidence=0.8,
                    source_text="测试",
                    source="manual",
                    status="active",
                    merge_reason="测试",
                    created_at=now,
                    updated_at=now,
                )
            )
        session.commit()
