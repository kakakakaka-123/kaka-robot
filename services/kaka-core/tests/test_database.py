import sqlite3

from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from kaka_core.storage.database import (
    EXPECTED_INPUT_COLUMNS,
    EXPECTED_MEMORY_CANDIDATE_COLUMNS,
    EXPECTED_MEMORY_COLUMNS,
    EXPECTED_OUTPUT_COLUMNS,
    create_database_engine,
    init_database,
)
from kaka_core.storage.repository import try_acquire_event_processing_lock


def test_init_database_migrates_legacy_messages_and_responses(tmp_path) -> None:
    db_path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                platform VARCHAR(32) NOT NULL,
                platform_user_id VARCHAR(128) NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY,
                platform VARCHAR(32) NOT NULL,
                scene_type VARCHAR(32) NOT NULL,
                scene_id VARCHAR(128) NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE messages (
                id INTEGER PRIMARY KEY,
                event_id VARCHAR(64) NOT NULL,
                user_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                content_type VARCHAR(32) NOT NULL,
                content_text TEXT,
                raw_event JSON,
                metadata JSON,
                created_at DATETIME
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE responses (
                id INTEGER PRIMARY KEY,
                response_id VARCHAR(64) NOT NULL,
                message_id INTEGER NOT NULL,
                should_reply BOOLEAN NOT NULL,
                content_text TEXT,
                metadata JSON,
                created_at DATETIME
            )
            """
        )
        conn.commit()

    engine = create_database_engine(f"sqlite:///{db_path}")

    init_database(engine)

    inspector = inspect(engine)
    assert "inputs" in inspector.get_table_names()
    assert "outputs" in inspector.get_table_names()
    assert "event_processing_locks" in inspector.get_table_names()
    assert "memory_candidates" in inspector.get_table_names()
    assert "memories" in inspector.get_table_names()
    assert "messages" not in inspector.get_table_names()
    assert "responses" not in inspector.get_table_names()

    columns = {column["name"] for column in inspector.get_columns("inputs")}
    assert "analysis_status" in columns
    assert "is_processed" not in columns
    assert "process_reason" not in columns
    assert [column["name"] for column in inspector.get_columns("inputs")] == EXPECTED_INPUT_COLUMNS

    output_columns = {column["name"] for column in inspector.get_columns("outputs")}
    assert "output_id" in output_columns
    assert "input_id" in output_columns
    assert "scene_id" in output_columns
    assert "user_id" in output_columns
    assert "output_origin" in output_columns
    assert "output_reason" in output_columns
    assert "no_reply_reason" in output_columns
    assert "response_id" not in output_columns
    assert "message_id" not in output_columns
    assert [column["name"] for column in inspector.get_columns("outputs")] == EXPECTED_OUTPUT_COLUMNS
    output_unique_indexes = [
        index
        for index in inspector.get_indexes("outputs")
        if index.get("unique") and index.get("column_names") == ["input_id"]
    ]
    assert output_unique_indexes != []

    assert [column["name"] for column in inspector.get_columns("memory_candidates")] == EXPECTED_MEMORY_CANDIDATE_COLUMNS
    candidate_unique_indexes = [
        index
        for index in inspector.get_indexes("memory_candidates")
        if index.get("unique") and index.get("column_names") == ["source_input_id"]
    ]
    assert candidate_unique_indexes == []

    memory_columns = {column["name"] for column in inspector.get_columns("memories")}
    assert {
        "source_candidate_id",
        "user_id",
        "scene_id",
        "memory_text",
        "normalized_text",
        "memory_type",
        "confidence",
        "source_text",
        "source",
        "status",
        "merge_reason",
    }.issubset(memory_columns)
    assert [column["name"] for column in inspector.get_columns("memories")] == EXPECTED_MEMORY_COLUMNS


def test_event_processing_lock_is_single_owner(tmp_path) -> None:
    db_path = tmp_path / "lock.sqlite3"
    engine = create_database_engine(f"sqlite:///{db_path}")
    init_database(engine)

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        first_owner = try_acquire_event_processing_lock(session, "event-1", lease_seconds=60)
        second_owner = try_acquire_event_processing_lock(session, "event-1", lease_seconds=60)

    assert first_owner is not None
    assert second_owner is None
