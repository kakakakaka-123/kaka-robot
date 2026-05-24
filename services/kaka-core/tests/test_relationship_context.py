from datetime import timedelta

from sqlalchemy.orm import sessionmaker

from kaka_core.config.settings import RelationshipSettings
from kaka_core.relationship.context import load_relationship_context
from kaka_core.storage.database import create_database_engine, init_database
from kaka_core.storage.models import InputRecord, MemoryRecord, SceneRecord, UserRecord, utc_now
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType


def default_relationship_settings(*, owners: frozenset[str] = frozenset()) -> RelationshipSettings:
    return RelationshipSettings(owner_user_ids=owners)


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


def test_owner_is_special_without_existing_database_user(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'owner.sqlite3'}")
    init_database(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        context = load_relationship_context(
            session,
            make_event("10001"),
            default_relationship_settings(owners=frozenset({"10001"})),
        )

    assert context.level == "special"
    assert context.is_owner is True


def test_non_owner_stays_normal_even_with_many_inputs_and_memories(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'normal.sqlite3'}")
    init_database(engine)
    seed_relationship_user(engine, input_count=200, recent_input_count=80, active_memory_count=20)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as session:
        context = load_relationship_context(
            session,
            make_event(),
            default_relationship_settings(),
        )

    assert context.level == "normal"
    assert context.is_owner is False


def seed_relationship_user(
    engine,
    *,
    input_count: int = 0,
    recent_input_count: int = 0,
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
        for index in range(max(input_count - recent_input_count, 0)):
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
