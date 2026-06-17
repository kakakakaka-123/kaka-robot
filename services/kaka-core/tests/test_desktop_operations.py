import sqlite3
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from kaka_core.api import desktop_routes
from kaka_core.api.desktop_routes import CompleteOperationRequest
from kaka_core.storage.database import create_database_engine, init_database
from kaka_core.storage.desktop_repository import create_desktop_operation
from kaka_core.storage.models import DesktopOperationRecord
from kaka_protocol import NotificationResult, Platform, SceneType


def test_create_desktop_operation_persists_requester_scene_type(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'desktop-scene-type.sqlite3'}")
    init_database(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with session_factory() as session:
        operation_id = create_desktop_operation(
            session,
            operation_type="create_file",
            params={"filename": "note.txt"},
            requester_user_id="10001",
            requester_scene_id="20002",
            requester_scene_type="group",
            requester_platform="qq",
        )
        session.commit()

        operation = session.get(DesktopOperationRecord, operation_id)

    assert operation is not None
    assert operation.requester_scene_type == "group"


def test_init_database_adds_desktop_operation_scene_type_to_legacy_table(tmp_path) -> None:
    db_path = tmp_path / "legacy-desktop.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE desktop_operations (
                id INTEGER PRIMARY KEY,
                operation_type VARCHAR(64) NOT NULL,
                params JSON NOT NULL,
                requester_user_id VARCHAR(128) NOT NULL,
                requester_scene_id VARCHAR(128) NOT NULL,
                requester_platform VARCHAR(32) NOT NULL,
                approved BOOLEAN NOT NULL,
                decision_reason TEXT,
                kaka_mood VARCHAR(32),
                status VARCHAR(32) NOT NULL,
                result JSON,
                error_message TEXT,
                created_at DATETIME,
                started_at DATETIME,
                completed_at DATETIME,
                permission_level INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO desktop_operations (
                id,
                operation_type,
                params,
                requester_user_id,
                requester_scene_id,
                requester_platform,
                approved,
                status,
                created_at,
                permission_level
            )
            VALUES (
                1,
                'create_file',
                '{}',
                '10001',
                '20002',
                'qq',
                1,
                'pending',
                '2026-06-17 00:00:00',
                1
            )
            """
        )
        conn.commit()

    engine = create_database_engine(f"sqlite:///{db_path}")

    init_database(engine)

    inspector = inspect(engine)
    columns = [column["name"] for column in inspector.get_columns("desktop_operations")]
    assert "requester_scene_type" in columns

    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_factory() as session:
        operation = session.get(DesktopOperationRecord, 1)

    assert operation is not None
    assert operation.requester_scene_type == "private"


@pytest.mark.anyio
async def test_completion_notification_uses_stored_scene_type_for_numeric_group_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_deliver_notification(request, settings):
        captured["request"] = request
        return NotificationResult(accepted=True, delivered=True, target=request.target)

    monkeypatch.setattr(desktop_routes, "deliver_notification", fake_deliver_notification)

    operation = DesktopOperationRecord(
        id=42,
        operation_type="create_file",
        params={},
        requester_user_id="10001",
        requester_scene_id="20002",
        requester_scene_type="group",
        requester_platform="qq",
        approved=True,
        status="completed",
        created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        permission_level=1,
    )

    await desktop_routes._send_completion_notification(
        operation,
        "写好了~",
        CompleteOperationRequest(success=True, result={}),
    )

    request = captured["request"]
    assert request.target.platform == Platform.QQ
    assert request.target.scene_id == "20002"
    assert request.target.scene_type == SceneType.GROUP


@pytest.mark.anyio
async def test_completion_notification_defaults_unknown_scene_type_to_private(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_deliver_notification(request, settings):
        captured["request"] = request
        return NotificationResult(accepted=True, delivered=True, target=request.target)

    monkeypatch.setattr(desktop_routes, "deliver_notification", fake_deliver_notification)

    operation = DesktopOperationRecord(
        id=43,
        operation_type="create_file",
        params={},
        requester_user_id="10001",
        requester_scene_id="10001",
        requester_scene_type="unknown",
        requester_platform="qq",
        approved=True,
        status="completed",
        created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        permission_level=1,
    )

    await desktop_routes._send_completion_notification(
        operation,
        "写好了~",
        CompleteOperationRequest(success=True, result={}),
    )

    request = captured["request"]
    assert request.target.scene_type == SceneType.PRIVATE


@pytest.mark.anyio
async def test_completion_notification_skips_desktop_platform_until_adapter_exists(monkeypatch) -> None:
    async def fail_if_called(_request, _settings):
        raise AssertionError("desktop notifications are not implemented")

    monkeypatch.setattr(desktop_routes, "deliver_notification", fail_if_called)

    operation = DesktopOperationRecord(
        id=44,
        operation_type="create_file",
        params={},
        requester_user_id="desktop-user",
        requester_scene_id="desktop-local",
        requester_scene_type="private",
        requester_platform="desktop",
        approved=True,
        status="completed",
        created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        permission_level=1,
    )

    await desktop_routes._send_completion_notification(
        operation,
        "写好了~",
        CompleteOperationRequest(success=True, result={}),
    )
