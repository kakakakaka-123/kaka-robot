from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from kaka_core.admin import service
from kaka_core.api.app import create_app
from kaka_core.config.settings import get_settings
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.models import (
    InputRecord,
    MemoryCandidateRecord,
    MemoryRecord,
    SceneRecord,
    UserRecord,
)


def create_test_client(monkeypatch, tmp_path, *, local_only: str = "true", token: str = "") -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'admin-api.sqlite3'}")
    monkeypatch.setenv("MEMORY_AUTO_ANALYSIS_ENABLED", "false")
    monkeypatch.setenv("MEMORY_AUTO_REVIEW_ENABLED", "false")
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("ADMIN_LOCAL_ONLY", local_only)
    if token:
        monkeypatch.setenv("ADMIN_API_TOKEN", token)
    else:
        monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)
    get_settings.cache_clear()
    init_database()
    seed_admin_data()
    return TestClient(create_app())


def test_admin_summary_and_lists(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    summary = client.get("/admin/api/summary")
    candidates = client.get("/admin/api/candidates", params={"status": "pending"})
    memories = client.get("/admin/api/memories", params={"status": "active"})
    conversations = client.get("/admin/api/conversations")

    assert summary.status_code == 200
    assert summary.json()["counts"]["pending_candidates"] == 1
    assert candidates.status_code == 200
    assert candidates.json()["items"][0]["candidate_memory"] == "用户正在开发卡咔 v2。"
    assert memories.status_code == 200
    assert memories.json()["items"][0]["memory_text"] == "用户喜欢直接的回答。"
    assert conversations.status_code == 200
    assert conversations.json()["items"][0]["id"] > 0


def test_admin_summary_redacts_database_password():
    url = "postgresql://kaka:secret-password@localhost:5432/kaka"

    redacted = service.redact_connection_url(url)

    assert "secret-password" not in redacted
    assert "***" in redacted


def test_admin_merge_candidate_and_archive_memory(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)
    with create_session_factory()() as session:
        candidate_id = session.scalar(select(MemoryCandidateRecord.id))
        memory_id = session.scalar(select(MemoryRecord.id))

    preview = client.post(
        "/admin/api/candidates/merge",
        json={"ids": [candidate_id], "apply": False},
    )
    applied = client.post(
        "/admin/api/candidates/merge",
        json={"ids": [candidate_id], "apply": True},
    )
    archived = client.post(
        "/admin/api/memories/status",
        json={"ids": [memory_id], "status": "archived"},
    )

    assert preview.status_code == 200
    assert preview.json()["plan"]["insert"] == 1
    assert applied.status_code == 200
    assert applied.json()["stats"]["inserted"] == 1
    assert archived.status_code == 200
    assert archived.json()["updated"] == 1


def test_admin_updates_input_and_candidate_status(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)
    with create_session_factory()() as session:
        candidate_id = session.scalar(select(MemoryCandidateRecord.id))
        input_id = session.scalar(select(InputRecord.id))

    input_status = client.post(
        "/admin/api/inputs/status",
        json={"ids": [input_id], "status": "skipped"},
    )
    candidate_status = client.post(
        "/admin/api/candidates/status",
        json={"ids": [candidate_id], "status": "rejected"},
    )

    assert input_status.status_code == 200
    assert input_status.json()["updated"] == 1
    assert candidate_status.status_code == 200
    assert candidate_status.json()["updated"] == 1

    with create_session_factory()() as session:
        assert session.get(InputRecord, input_id).analysis_status == "skipped"
        assert session.get(MemoryCandidateRecord, candidate_id).status == "rejected"


def test_admin_search_memories(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    response = client.post(
        "/admin/api/memories/search",
        json={
            "user_id": "10001",
            "text": "我想要直接一点的回答",
            "group_id": "20002",
            "limit": 5,
            "min_score": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["memory"]["memory_text"] == "用户喜欢直接的回答。"


def test_admin_api_requires_token_when_local_only_disabled(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path, local_only="false")

    response = client.get("/admin/api/summary")

    assert response.status_code == 403
    assert response.json()["detail"] == "admin api token is required when local-only is disabled"


def test_admin_api_accepts_configured_token(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path, local_only="false", token="secret")

    missing = client.get("/admin/api/summary")
    accepted = client.get("/admin/api/summary", headers={"X-Kaka-Admin-Token": "secret"})

    assert missing.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json()["settings"]["admin_api_token_configured"] is True


def test_unknown_admin_api_route_returns_404(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    response = client.get("/admin/api/not-found")

    assert response.status_code == 404
    assert response.json()["detail"] == "admin api route not found"


def seed_admin_data() -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        user = UserRecord(
            platform="qq",
            platform_user_id="10001",
            display_name="测试用户",
            created_at=datetime(2026, 5, 3, 1, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 3, 1, 0, tzinfo=timezone.utc),
        )
        scene = SceneRecord(
            platform="qq",
            scene_type="group",
            scene_id="20002",
            created_at=datetime(2026, 5, 3, 1, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 5, 3, 1, 0, tzinfo=timezone.utc),
        )
        session.add_all([user, scene])
        session.flush()

        input_record = InputRecord(
            event_id="admin-input-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="我正在开发卡咔 v2。",
            raw_event={},
            extra_metadata={},
            analysis_status="analyzed",
            created_at=datetime(2026, 5, 3, 1, 1, tzinfo=timezone.utc),
        )
        session.add(input_record)
        session.flush()

        session.add(
            MemoryCandidateRecord(
                source_input_id=input_record.id,
                source_user_id=user.id,
                source_scene_id=scene.id,
                source_text=input_record.content_text or "",
                candidate_memory="用户正在开发卡咔 v2。",
                memory_type="user_fact",
                confidence=0.85,
                reason="项目长期事实",
                analysis_model="test",
                analysis_prompt_version="test",
                status="pending",
                created_at=datetime(2026, 5, 3, 1, 2, tzinfo=timezone.utc),
                updated_at=datetime(2026, 5, 3, 1, 2, tzinfo=timezone.utc),
            )
        )
        session.add(
            MemoryRecord(
                user_id=user.id,
                scene_id=scene.id,
                memory_text="用户喜欢直接的回答。",
                normalized_text="用户喜欢直接的回答",
                memory_type="stable_preference",
                confidence=0.9,
                source_text="我喜欢直接的回答。",
                source="candidate",
                status="active",
                merge_reason="测试记忆",
                created_at=datetime(2026, 5, 3, 1, 3, tzinfo=timezone.utc),
                updated_at=datetime(2026, 5, 3, 1, 3, tzinfo=timezone.utc),
            )
        )
        session.commit()
