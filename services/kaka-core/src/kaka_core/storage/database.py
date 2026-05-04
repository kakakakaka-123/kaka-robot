from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from kaka_core.config.settings import get_settings
from kaka_core.storage.models import Base

EXPECTED_INPUT_COLUMNS = [
    "id",
    "event_id",
    "user_id",
    "scene_id",
    "content_type",
    "content_text",
    "raw_event",
    "metadata",
    "analysis_status",
    "created_at",
]

EXPECTED_OUTPUT_COLUMNS = [
    "id",
    "output_id",
    "input_id",
    "scene_id",
    "user_id",
    "output_origin",
    "output_reason",
    "should_reply",
    "no_reply_reason",
    "content_text",
    "metadata",
    "created_at",
]

EXPECTED_MEMORY_COLUMNS = [
    "id",
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
    "created_at",
    "updated_at",
]

EXPECTED_MEMORY_CANDIDATE_COLUMNS = [
    "id",
    "source_input_id",
    "source_user_id",
    "source_scene_id",
    "source_text",
    "candidate_memory",
    "memory_type",
    "confidence",
    "reason",
    "analysis_model",
    "analysis_prompt_version",
    "status",
    "created_at",
    "updated_at",
]


def create_database_engine(database_url: str | None = None) -> Engine:
    """创建数据库引擎，并确保本地数据库文件所在目录存在。"""

    url = database_url or get_settings().database.url
    if url.startswith("sqlite:///"):
        db_path = Path(url.removeprefix("sqlite:///"))
        db_path.parent.mkdir(parents=True, exist_ok=True)

    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def init_database(engine: Engine | None = None) -> None:
    """初始化数据库表，并对本地 SQLite 做轻量迁移。

    项目还没有引入 Alembic。这里先兼容旧表名和旧字段，再把本地 SQLite
    整理成当前模型期望的表结构。整理过程会保留已有数据。
    """

    target_engine = engine or create_database_engine()
    migrate_sqlite_schema(target_engine)
    Base.metadata.create_all(target_engine)
    migrate_sqlite_schema(target_engine)


def migrate_sqlite_schema(engine: Engine) -> None:
    """补齐当前版本需要的 SQLite 表名、字段、字段顺序和索引。"""

    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        table_names = get_sqlite_table_names(connection)

        if "messages" in table_names and "inputs" not in table_names:
            connection.execute(text("ALTER TABLE messages RENAME TO inputs"))
            table_names.remove("messages")
            table_names.add("inputs")

        if "responses" in table_names and "outputs" not in table_names:
            connection.execute(text("ALTER TABLE responses RENAME TO outputs"))
            table_names.remove("responses")
            table_names.add("outputs")

        if "inputs" in table_names:
            input_columns = get_sqlite_column_names(connection, "inputs")
            if "analysis_status" not in input_columns:
                connection.execute(
                    text(
                        "ALTER TABLE inputs "
                        "ADD COLUMN analysis_status VARCHAR(32) NOT NULL DEFAULT 'not_analyzed'"
                    )
                )
            connection.execute(
                text(
                    "UPDATE inputs SET analysis_status = 'not_analyzed' "
                    "WHERE analysis_status IN ('pending', 'done', 'legacy')"
                )
            )

        if "outputs" in table_names:
            output_columns = get_sqlite_column_names(connection, "outputs")
            if "response_id" in output_columns and "output_id" not in output_columns:
                connection.execute(text("ALTER TABLE outputs RENAME COLUMN response_id TO output_id"))
            if "message_id" in output_columns and "input_id" not in output_columns:
                connection.execute(text("ALTER TABLE outputs RENAME COLUMN message_id TO input_id"))
            output_columns = get_sqlite_column_names(connection, "outputs")

            if "scene_id" not in output_columns:
                connection.execute(text("ALTER TABLE outputs ADD COLUMN scene_id INTEGER"))
                connection.execute(
                    text(
                        "UPDATE outputs "
                        "SET scene_id = (SELECT scene_id FROM inputs WHERE inputs.id = outputs.input_id) "
                        "WHERE input_id IS NOT NULL"
                    )
                )
            if "user_id" not in output_columns:
                connection.execute(text("ALTER TABLE outputs ADD COLUMN user_id INTEGER"))
                connection.execute(
                    text(
                        "UPDATE outputs "
                        "SET user_id = (SELECT user_id FROM inputs WHERE inputs.id = outputs.input_id) "
                        "WHERE input_id IS NOT NULL"
                    )
                )
            if "output_origin" not in output_columns:
                connection.execute(
                    text(
                        "ALTER TABLE outputs "
                        "ADD COLUMN output_origin VARCHAR(32) NOT NULL DEFAULT 'passive'"
                    )
                )
            if "output_reason" not in output_columns:
                connection.execute(
                    text(
                        "ALTER TABLE outputs "
                        "ADD COLUMN output_reason VARCHAR(32) NOT NULL DEFAULT 'unknown'"
                    )
                )
                input_columns = get_sqlite_column_names(connection, "inputs")
                if "process_reason" in input_columns:
                    connection.execute(
                        text(
                            "UPDATE outputs "
                            "SET output_reason = COALESCE("
                            "(SELECT process_reason FROM inputs WHERE inputs.id = outputs.input_id), "
                            "'unknown'"
                            ") "
                            "WHERE input_id IS NOT NULL"
                        )
                    )
            if "no_reply_reason" not in output_columns:
                connection.execute(text("ALTER TABLE outputs ADD COLUMN no_reply_reason VARCHAR(64)"))

            connection.execute(
                text("UPDATE outputs SET output_origin = 'passive' WHERE output_origin = 'trigger'")
            )
            connection.execute(
                text(
                    "UPDATE outputs SET output_reason = 'unknown' "
                    "WHERE output_reason IS NULL OR output_reason = '' OR output_reason = 'chat'"
                )
            )

        table_names = get_sqlite_table_names(connection)
        if "inputs" in table_names and should_rebuild_inputs_table(connection):
            rebuild_inputs_table(connection)

        table_names = get_sqlite_table_names(connection)
        if "outputs" in table_names and should_rebuild_outputs_table(connection):
            rebuild_outputs_table(connection)

        table_names = get_sqlite_table_names(connection)
        if "memory_candidates" in table_names and should_rebuild_memory_candidates_table(connection):
            rebuild_memory_candidates_table(connection)

        table_names = get_sqlite_table_names(connection)
        if "memories" in table_names and should_rebuild_memories_table(connection):
            rebuild_memories_table(connection)

        create_sqlite_indexes(connection)


def should_rebuild_inputs_table(connection) -> bool:
    """判断 inputs 是否需要重建。

    SQLite 不能稳定地原地删除字段或调整字段顺序，所以这类整理要通过
    创建新表、复制数据、替换旧表完成。
    """

    columns = get_sqlite_ordered_column_names(connection, "inputs")
    return columns != EXPECTED_INPUT_COLUMNS


def should_rebuild_outputs_table(connection) -> bool:
    """判断 outputs 是否需要重建。"""

    columns = get_sqlite_ordered_column_names(connection, "outputs")
    if columns != EXPECTED_OUTPUT_COLUMNS:
        return True

    column_info = get_sqlite_column_info(connection, "outputs")
    input_id = column_info.get("input_id")
    scene_id = column_info.get("scene_id")
    if input_id is not None and bool(input_id["notnull"]):
        return True
    if scene_id is not None and not bool(scene_id["notnull"]):
        return True
    return False


def should_rebuild_memories_table(connection) -> bool:
    """判断 memories 是否需要重建。"""

    columns = get_sqlite_ordered_column_names(connection, "memories")
    return columns != EXPECTED_MEMORY_COLUMNS


def should_rebuild_memory_candidates_table(connection) -> bool:
    """判断 memory_candidates 是否需要重建。

    旧版本对 source_input_id 有唯一约束，导致一条输入最多只能抽出一条候选。
    现在改为允许同一 input 产生多条不同候选，所以需要移除旧唯一索引。
    """

    columns = get_sqlite_ordered_column_names(connection, "memory_candidates")
    if columns != EXPECTED_MEMORY_CANDIDATE_COLUMNS:
        return True
    return has_unique_index_on_columns(connection, "memory_candidates", ["source_input_id"])


def rebuild_inputs_table(connection) -> None:
    """重建 inputs 表，删除废弃字段并固定字段顺序。"""

    connection.execute(text("DROP TABLE IF EXISTS inputs__new"))
    connection.execute(
        text(
            """
            CREATE TABLE inputs__new (
                id INTEGER NOT NULL,
                event_id VARCHAR(64) NOT NULL,
                user_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                content_type VARCHAR(32) NOT NULL,
                content_text TEXT,
                raw_event JSON NOT NULL,
                metadata JSON NOT NULL,
                analysis_status VARCHAR(32) NOT NULL DEFAULT 'not_analyzed',
                created_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (event_id),
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(scene_id) REFERENCES scenes (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO inputs__new (
                id,
                event_id,
                user_id,
                scene_id,
                content_type,
                content_text,
                raw_event,
                metadata,
                analysis_status,
                created_at
            )
            SELECT
                id,
                event_id,
                user_id,
                scene_id,
                content_type,
                content_text,
                COALESCE(raw_event, '{}'),
                COALESCE(metadata, '{}'),
                CASE
                    WHEN analysis_status IS NULL THEN 'not_analyzed'
                    WHEN analysis_status = '' THEN 'not_analyzed'
                    WHEN analysis_status IN ('pending', 'done', 'legacy') THEN 'not_analyzed'
                    ELSE analysis_status
                END,
                COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM inputs
            """
        )
    )
    connection.execute(text("DROP TABLE inputs"))
    connection.execute(text("ALTER TABLE inputs__new RENAME TO inputs"))


def rebuild_outputs_table(connection) -> None:
    """重建 outputs 表，固定长期使用的字段顺序。"""

    connection.execute(text("DROP TABLE IF EXISTS outputs__new"))
    connection.execute(
        text(
            """
            CREATE TABLE outputs__new (
                id INTEGER NOT NULL,
                output_id VARCHAR(64) NOT NULL,
                input_id INTEGER,
                scene_id INTEGER NOT NULL,
                user_id INTEGER,
                output_origin VARCHAR(32) NOT NULL DEFAULT 'passive',
                output_reason VARCHAR(32) NOT NULL DEFAULT 'unknown',
                should_reply BOOLEAN NOT NULL,
                no_reply_reason VARCHAR(64),
                content_text TEXT,
                metadata JSON NOT NULL,
                created_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (output_id),
                FOREIGN KEY(input_id) REFERENCES inputs (id),
                FOREIGN KEY(scene_id) REFERENCES scenes (id),
                FOREIGN KEY(user_id) REFERENCES users (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO outputs__new (
                id,
                output_id,
                input_id,
                scene_id,
                user_id,
                output_origin,
                output_reason,
                should_reply,
                no_reply_reason,
                content_text,
                metadata,
                created_at
            )
            SELECT
                id,
                output_id,
                input_id,
                COALESCE(
                    scene_id,
                    (SELECT inputs.scene_id FROM inputs WHERE inputs.id = outputs.input_id)
                ),
                COALESCE(
                    user_id,
                    (SELECT inputs.user_id FROM inputs WHERE inputs.id = outputs.input_id)
                ),
                COALESCE(NULLIF(output_origin, ''), 'passive'),
                COALESCE(NULLIF(output_reason, ''), 'unknown'),
                COALESCE(should_reply, 0),
                no_reply_reason,
                content_text,
                COALESCE(metadata, '{}'),
                COALESCE(created_at, CURRENT_TIMESTAMP)
            FROM outputs
            """
        )
    )
    connection.execute(text("DROP TABLE outputs"))
    connection.execute(text("ALTER TABLE outputs__new RENAME TO outputs"))


def rebuild_memory_candidates_table(connection) -> None:
    """重建 memory_candidates 表，移除 source_input_id 的旧唯一约束。"""

    connection.execute(text("DROP TABLE IF EXISTS memory_candidates__new"))
    connection.execute(
        text(
            """
            CREATE TABLE memory_candidates__new (
                id INTEGER NOT NULL,
                source_input_id INTEGER NOT NULL,
                source_user_id INTEGER NOT NULL,
                source_scene_id INTEGER NOT NULL,
                source_text TEXT NOT NULL,
                candidate_memory TEXT NOT NULL,
                memory_type VARCHAR(64) NOT NULL,
                confidence FLOAT NOT NULL,
                reason TEXT NOT NULL,
                analysis_model VARCHAR(128) NOT NULL,
                analysis_prompt_version VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'pending',
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                FOREIGN KEY(source_input_id) REFERENCES inputs (id),
                FOREIGN KEY(source_user_id) REFERENCES users (id),
                FOREIGN KEY(source_scene_id) REFERENCES scenes (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO memory_candidates__new (
                id,
                source_input_id,
                source_user_id,
                source_scene_id,
                source_text,
                candidate_memory,
                memory_type,
                confidence,
                reason,
                analysis_model,
                analysis_prompt_version,
                status,
                created_at,
                updated_at
            )
            SELECT
                id,
                source_input_id,
                source_user_id,
                source_scene_id,
                source_text,
                candidate_memory,
                memory_type,
                COALESCE(confidence, 0.0),
                reason,
                analysis_model,
                analysis_prompt_version,
                COALESCE(NULLIF(status, ''), 'pending'),
                COALESCE(created_at, CURRENT_TIMESTAMP),
                COALESCE(updated_at, CURRENT_TIMESTAMP)
            FROM memory_candidates
            """
        )
    )
    connection.execute(text("DROP TABLE memory_candidates"))
    connection.execute(text("ALTER TABLE memory_candidates__new RENAME TO memory_candidates"))


def rebuild_memories_table(connection) -> None:
    """重建 memories 表，补齐正式长期记忆字段并固定字段顺序。"""

    old_columns = get_sqlite_column_names(connection, "memories")
    connection.execute(text("DROP TABLE IF EXISTS memories__new"))
    connection.execute(
        text(
            """
            CREATE TABLE memories__new (
                id INTEGER NOT NULL,
                source_candidate_id INTEGER,
                user_id INTEGER NOT NULL,
                scene_id INTEGER,
                memory_text TEXT NOT NULL,
                normalized_text TEXT NOT NULL,
                memory_type VARCHAR(64) NOT NULL,
                confidence FLOAT NOT NULL,
                source_text TEXT,
                source VARCHAR(32) NOT NULL DEFAULT 'candidate',
                status VARCHAR(32) NOT NULL DEFAULT 'active',
                merge_reason TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                PRIMARY KEY (id),
                UNIQUE (source_candidate_id),
                FOREIGN KEY(source_candidate_id) REFERENCES memory_candidates (id),
                FOREIGN KEY(user_id) REFERENCES users (id),
                FOREIGN KEY(scene_id) REFERENCES scenes (id)
            )
            """
        )
    )
    select_source_candidate_id = (
        "source_candidate_id" if "source_candidate_id" in old_columns else "NULL"
    )
    select_scene_id = "scene_id" if "scene_id" in old_columns else "NULL"
    select_normalized_text = (
        "normalized_text" if "normalized_text" in old_columns else "LOWER(TRIM(memory_text))"
    )
    select_confidence = "COALESCE(confidence, 0.0)" if "confidence" in old_columns else "0.0"
    select_source_text = "source_text" if "source_text" in old_columns else "NULL"
    select_source = "COALESCE(NULLIF(source, ''), 'candidate')" if "source" in old_columns else "'candidate'"
    select_status = "COALESCE(NULLIF(status, ''), 'active')" if "status" in old_columns else "'active'"
    select_merge_reason = "merge_reason" if "merge_reason" in old_columns else "NULL"
    select_created_at = (
        "COALESCE(created_at, CURRENT_TIMESTAMP)" if "created_at" in old_columns else "CURRENT_TIMESTAMP"
    )
    select_updated_at = (
        "COALESCE(updated_at, CURRENT_TIMESTAMP)" if "updated_at" in old_columns else "CURRENT_TIMESTAMP"
    )
    connection.execute(
        text(
            f"""
            INSERT INTO memories__new (
                id,
                source_candidate_id,
                user_id,
                scene_id,
                memory_text,
                normalized_text,
                memory_type,
                confidence,
                source_text,
                source,
                status,
                merge_reason,
                created_at,
                updated_at
            )
            SELECT
                id,
                {select_source_candidate_id},
                user_id,
                {select_scene_id},
                memory_text,
                {select_normalized_text},
                memory_type,
                {select_confidence},
                {select_source_text},
                {select_source},
                {select_status},
                {select_merge_reason},
                {select_created_at},
                {select_updated_at}
            FROM memories
            """
        )
    )
    connection.execute(text("DROP TABLE memories"))
    connection.execute(text("ALTER TABLE memories__new RENAME TO memories"))


def create_sqlite_indexes(connection) -> None:
    """补齐当前查询会用到的 SQLite 索引。"""

    table_names = get_sqlite_table_names(connection)
    if "inputs" in table_names:
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_inputs_event_id ON inputs (event_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_inputs_user_id ON inputs (user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_inputs_scene_id ON inputs (scene_id)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_inputs_analysis_status ON inputs (analysis_status)")
        )

    if "outputs" in table_names:
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_outputs_output_id ON outputs (output_id)")
        )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_outputs_input_id "
                "ON outputs (input_id) WHERE input_id IS NOT NULL"
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_outputs_input_id ON outputs (input_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_outputs_scene_id ON outputs (scene_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_outputs_user_id ON outputs (user_id)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_outputs_output_origin ON outputs (output_origin)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_outputs_output_reason ON outputs (output_reason)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_outputs_no_reply_reason ON outputs (no_reply_reason)")
        )

    if "memories" in table_names:
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memories_source_candidate_id ON memories (source_candidate_id)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memories_user_id ON memories (user_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memories_scene_id ON memories (scene_id)"))
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memories_normalized_text ON memories (normalized_text)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_memories_memory_type ON memories (memory_type)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memories_source ON memories (source)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_memories_status ON memories (status)"))

    if "memory_candidates" in table_names:
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_candidates_source_input_id "
                "ON memory_candidates (source_input_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_candidates_source_user_id "
                "ON memory_candidates (source_user_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_candidates_source_scene_id "
                "ON memory_candidates (source_scene_id)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_candidates_memory_type "
                "ON memory_candidates (memory_type)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_memory_candidates_status "
                "ON memory_candidates (status)"
            )
        )


def get_sqlite_table_names(connection) -> set[str]:
    """读取 SQLite 当前表名。"""

    rows = connection.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))
    return {str(row[0]) for row in rows}


def get_sqlite_column_names(connection, table_name: str) -> set[str]:
    """读取 SQLite 指定表的字段名。"""

    rows = connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {str(row[1]) for row in rows}


def get_sqlite_ordered_column_names(connection, table_name: str) -> list[str]:
    """按真实字段顺序读取 SQLite 指定表的字段名。"""

    rows = connection.execute(text(f"PRAGMA table_info({table_name})"))
    return [str(row[1]) for row in rows]


def get_sqlite_column_info(connection, table_name: str) -> dict[str, dict[str, object]]:
    """读取 SQLite 字段细节。"""

    rows = connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {
        str(row[1]): {
            "type": row[2],
            "notnull": row[3],
            "default": row[4],
            "pk": row[5],
        }
        for row in rows
    }


def has_unique_index_on_columns(connection, table_name: str, columns: list[str]) -> bool:
    """判断 SQLite 表上是否存在指定字段组合的唯一索引。"""

    index_rows = connection.execute(text(f"PRAGMA index_list({table_name})")).fetchall()
    expected = list(columns)
    for row in index_rows:
        is_unique = bool(row[2])
        if not is_unique:
            continue
        index_name = str(row[1])
        info_rows = connection.execute(text(f"PRAGMA index_info({index_name})")).fetchall()
        indexed_columns = [str(info_row[2]) for info_row in info_rows]
        if indexed_columns == expected:
            return True
    return False


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    """创建数据库会话工厂。"""

    target_engine = engine or create_database_engine()
    return sessionmaker(bind=target_engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """获取一次数据库会话。"""

    session_factory = create_session_factory()
    with session_factory() as session:
        yield session
