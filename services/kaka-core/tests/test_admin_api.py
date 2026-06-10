from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select

from kaka_core.admin import service
from kaka_core.api.app import create_app
from kaka_core.config.settings import get_settings
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.models import (
    AutoJobRunRecord,
    InputRecord,
    MemoryCandidateRecord,
    MemoryRecord,
    OutputRecord,
    SceneRecord,
    UserRecord,
)


def create_test_client(monkeypatch, tmp_path, *, local_only: str = "true", token: str = "") -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'admin-api.sqlite3'}")
    monkeypatch.setenv("MEMORY_AUTO_ANALYSIS_ENABLED", "false")
    monkeypatch.setenv("MEMORY_AUTO_REVIEW_ENABLED", "false")
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("ADMIN_LOCAL_ONLY", local_only)
    monkeypatch.setenv("KAKA_OWNER_USER_IDS", "")
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
    with create_session_factory()() as session:
        session.add(
            AutoJobRunRecord(
                job_name="auto_analysis",
                status="skipped",
                reason="未达到触发门槛 50",
                checked_count=3,
                processed_runs=0,
                inserted_count=0,
                updated_count=0,
                skipped_count=0,
                error_count=0,
                extra_metadata={},
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    summary = client.get("/admin/api/summary")
    candidates = client.get("/admin/api/candidates", params={"status": "pending"})
    memories = client.get("/admin/api/memories", params={"status": "active"})
    conversations = client.get("/admin/api/conversations")

    assert summary.status_code == 200
    assert summary.json()["counts"]["pending_candidates"] == 1
    assert summary.json()["settings"]["memory_auto_analysis_interval_seconds"] == 0
    assert summary.json()["settings"]["memory_auto_analysis_batch_limit"] == 50
    assert summary.json()["settings"]["memory_auto_review_batch_size"] == 10
    assert summary.json()["recent_auto_job_runs"][0]["job_name"] == "auto_analysis"
    assert summary.json()["recent_auto_job_runs"][0]["status"] == "skipped"
    assert candidates.status_code == 200
    assert candidates.json()["items"][0]["candidate_memory"] == "用户正在开发卡咔。"
    assert memories.status_code == 200
    assert memories.json()["items"][0]["memory_text"] == "用户喜欢直接的回答。"
    assert conversations.status_code == 200
    assert conversations.json()["items"][0]["id"] > 0


def test_admin_summary_redacts_database_password():
    url = "postgresql://kaka:secret-password@localhost:5432/kaka"

    redacted = service.redact_connection_url(url)

    assert "secret-password" not in redacted
    assert "***" in redacted


def test_admin_conversation_detail_resolves_reply_metadata(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)
    with create_session_factory()() as session:
        user = session.scalar(select(UserRecord))
        scene = session.scalar(select(SceneRecord))
        short_context_input = session.scalar(select(InputRecord))
        memory = session.scalar(select(MemoryRecord))
        assert user is not None
        assert scene is not None
        assert short_context_input is not None
        assert memory is not None

        current_input = InputRecord(
            event_id="admin-input-2",
            user=user,
            scene=scene,
            content_type="text",
            content_text="你还记得我的回复偏好吗？",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=datetime(2026, 5, 3, 1, 5, tzinfo=timezone.utc),
        )
        session.add(current_input)
        session.flush()
        session.add(
            OutputRecord(
                output_id="admin-output-2",
                input=current_input,
                scene=scene,
                user=user,
                output_origin="passive",
                output_reason="keyword",
                should_reply=True,
                content_text="记得，你喜欢直接的回答。",
                extra_metadata={
                    "llm_model": "test-model",
                    "used_memory_ids": [memory.id],
                    "memory_count": 1,
                    "short_context_input_ids": [short_context_input.id],
                    "short_context_count": 1,
                    "relationship_level": "special",
                },
                created_at=datetime(2026, 5, 3, 1, 6, tzinfo=timezone.utc),
            )
        )
        session.commit()
        current_input_id = current_input.id

    response = client.get(f"/admin/api/conversations/{current_input_id}")
    data = response.json()

    assert response.status_code == 200
    assert data["conversation"]["id"] == current_input_id
    assert data["conversation"]["output"]["content_text"] == "记得，你喜欢直接的回答。"
    assert data["metadata"]["llm_model"] == "test-model"
    assert data["metadata"]["relationship_level"] == "special"
    assert data["used_memory_ids"] == [1]
    assert data["used_memories"][0]["memory_text"] == "用户喜欢直接的回答。"
    assert data["short_context_input_ids"] == [1]
    assert data["short_context"][0]["content_text"] == "我正在开发卡咔。"


def test_admin_conversations_support_pagination(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)
    with create_session_factory()() as session:
        user = session.scalar(select(UserRecord))
        scene = session.scalar(select(SceneRecord))
        assert user is not None
        assert scene is not None
        for index in range(4):
            input_record = InputRecord(
                event_id=f"admin-replied-input-{index}",
                user=user,
                scene=scene,
                content_type="text",
                content_text=f"分页回复输入 {index}",
                raw_event={},
                extra_metadata={},
                analysis_status="analyzed",
                created_at=datetime(2026, 5, 3, 1, 10 + index, tzinfo=timezone.utc),
            )
            session.add(input_record)
            session.flush()
            session.add(
                OutputRecord(
                    output_id=f"admin-replied-output-{index}",
                    input=input_record,
                    scene=scene,
                    user=user,
                    output_origin="passive",
                    output_reason="keyword",
                    should_reply=True,
                    content_text=f"分页回复输出 {index}",
                    extra_metadata={},
                    created_at=datetime(2026, 5, 3, 1, 10 + index, tzinfo=timezone.utc),
                )
            )
        session.commit()

    first_page = client.get("/admin/api/conversations", params={"reply_state": "replied", "limit": 2, "offset": 0})
    second_page = client.get("/admin/api/conversations", params={"reply_state": "replied", "limit": 2, "offset": 2})
    first_data = first_page.json()
    second_data = second_page.json()

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_data["total"] == 4
    assert first_data["limit"] == 2
    assert first_data["offset"] == 0
    assert [item["id"] for item in first_data["items"]] == [5, 4]
    assert second_data["total"] == 4
    assert second_data["limit"] == 2
    assert second_data["offset"] == 2
    assert [item["id"] for item in second_data["items"]] == [3, 2]


def test_admin_can_trigger_auto_analysis_manually(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    response = client.post(
        "/admin/api/auto-jobs/auto_analysis/trigger",
        json={"force": True},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["job_name"] == "auto_analysis"
    assert data["job_label"] == "自动候选分析"
    assert data["force"] is True
    assert data["summary"]["ran"] is False
    assert data["summary"]["reason"] == "没有可处理记录"
    assert data["latest_run"]["job_name"] == "auto_analysis"
    assert data["latest_run"]["status"] == "skipped"
    assert data["latest_run"]["metadata"]["force"] is True


def test_admin_can_trigger_auto_review_manually(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    response = client.post(
        "/admin/api/auto-jobs/auto_review/trigger",
        json={"force": True},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["job_name"] == "auto_review"
    assert data["job_label"] == "自动候选复核"
    assert data["force"] is True
    assert data["summary"]["ran"] is False
    assert data["summary"]["checked_count"] == 1
    assert data["summary"]["reason"] == "LLM 未启用或缺少 LLM_API_KEY"
    assert data["latest_run"]["job_name"] == "auto_review"
    assert data["latest_run"]["status"] == "skipped"
    assert data["latest_run"]["metadata"]["force"] is True


def test_admin_rejects_unknown_auto_job(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    response = client.post(
        "/admin/api/auto-jobs/not-a-job/trigger",
        json={"force": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported auto job: not-a-job"


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


def test_admin_can_create_and_update_memory(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    created = client.post(
        "/admin/api/memories",
        json={
            "user_id": "10002",
            "display_name": "新用户",
            "group_id": "20003",
            "memory_text": "新用户喜欢先看结论。",
            "memory_type": "stable_preference",
            "confidence": 0.7,
            "source_text": "请先说结论",
        },
    )
    created_item = created.json()["item"]
    updated = client.patch(
        f"/admin/api/memories/{created_item['id']}",
        json={
            "memory_text": "新用户喜欢回复先给结论。",
            "memory_type": "stable_preference",
            "confidence": 0.9,
            "merge_reason": "手动修正",
        },
    )

    assert created.status_code == 200
    assert created_item["source"] == "manual"
    assert created_item["user"]["platform_user_id"] == "10002"
    assert created_item["scene"]["scene_id"] == "20003"
    assert updated.status_code == 200
    assert updated.json()["item"]["memory_text"] == "新用户喜欢回复先给结论。"
    assert updated.json()["item"]["normalized_text"] == "新用户喜欢回复先给结论"
    assert updated.json()["item"]["confidence"] == 0.9
    assert updated.json()["item"]["merge_reason"] == "手动修正"


def test_admin_create_memory_validates_required_text(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)

    response = client.post(
        "/admin/api/memories",
        json={
            "user_id": "10002",
            "memory_text": "   ",
            "memory_type": "user_fact",
            "confidence": 0.8,
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "memory_text is required"


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


def test_admin_reply_context_preview_reuses_reply_builder(monkeypatch, tmp_path):
    persona_path = tmp_path / "preview-persona.md"
    persona_path.write_text("你是管理台预览里的卡咔。", encoding="utf-8")
    monkeypatch.setenv("KAKA_PERSONA_PROMPT_PATH", str(persona_path))
    client = create_test_client(monkeypatch, tmp_path)
    with create_session_factory()() as session:
        input_record = session.scalar(select(InputRecord))
        assert input_record is not None
        input_record.created_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        session.commit()

    response = client.post(
        "/admin/api/reply-context/preview",
        json={
            "user_id": "10001",
            "display_name": "测试用户",
            "text": "我想要直接一点的回答",
            "group_id": "20002",
        },
    )
    data = response.json()

    assert response.status_code == 200
    assert data["memory_injection_enabled"] is True
    assert data["memory_count"] == 1
    assert data["used_memory_ids"] == [1]
    assert data["messages"][0]["role"] == "system"
    assert data["messages"][0]["content"].startswith("你是管理台预览里的卡咔。")
    assert "回复风格规范" in data["messages"][0]["content"]
    assert "可参考的长期记忆" in data["messages"][0]["content"]
    assert "用户喜欢直接的回答。" in data["messages"][0]["content"]
    assert "本次场景策略" in data["messages"][0]["content"]
    assert "发送前自检" in data["messages"][0]["content"]
    assert data["messages"][1]["role"] == "user"
    assert "近期对话" in data["messages"][1]["content"]
    assert "测试用户：我正在开发卡咔。" in data["messages"][1]["content"]
    assert "当前用户消息：我想要直接一点的回答" in data["messages"][1]["content"]
    assert data["metadata"]["short_context_enabled"] is True
    assert data["metadata"]["short_context_count"] == 1
    assert data["metadata"]["short_context_input_ids"] == [1]
    assert data["metadata"]["relationship_level"] == "normal"
    assert data["metadata"]["persona_prompt_source"] == "file"
    assert data["metadata"]["persona_prompt_path"] == str(persona_path)
    assert data["metadata"]["persona_prompt_fallback_used"] is False
    assert data["metadata"]["context_layer_names"] == [
        "persona",
        "reply_style",
        "relationship",
        "memory",
        "scene_strategy",
        "output_guard",
        "recent_context",
        "current_message",
    ]
    assert [layer["name"] for layer in data["layers"]] == data["metadata"]["context_layer_names"]
    assert data["layers"][0]["title"] == "基础人设"
    assert data["layers"][1]["title"] == "回复风格规范"
    assert data["layers"][2]["title"] == "关系上下文"
    assert data["layers"][3]["title"] == "长期记忆"
    assert data["layers"][4]["title"] == "本次场景策略"
    assert data["layers"][5]["title"] == "发送前自检"
    assert data["layers"][6]["title"] == "短期上下文"
    assert data["layers"][7]["title"] == "当前消息"
    assert "relationship_input_count" not in data["metadata"]
    assert "当前说话者关系" in data["messages"][0]["content"]


def test_admin_memories_are_ordered_by_newest_id_first(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)
    session_factory = create_session_factory()
    with session_factory() as session:
        user = session.scalar(select(UserRecord))
        scene = session.scalar(select(SceneRecord))
        assert user is not None
        assert scene is not None
        session.add(
            MemoryRecord(
                user_id=user.id,
                scene_id=scene.id,
                memory_text="用户后加入的测试记忆。",
                normalized_text="用户后加入的测试记忆",
                memory_type="user_fact",
                confidence=0.8,
                source_text="测试",
                source="candidate",
                status="active",
                merge_reason="测试",
                created_at=datetime(2026, 5, 3, 1, 4, tzinfo=timezone.utc),
                updated_at=datetime(2026, 5, 3, 1, 4, tzinfo=timezone.utc),
            )
        )
        session.commit()

    response = client.get("/admin/api/memories", params={"status": "active"})
    ids = [item["id"] for item in response.json()["items"]]

    assert response.status_code == 200
    assert ids == sorted(ids, reverse=True)


def test_admin_memories_support_pagination(monkeypatch, tmp_path):
    client = create_test_client(monkeypatch, tmp_path)
    seed_extra_memories(4)

    first_page = client.get("/admin/api/memories", params={"status": "active", "limit": 2, "offset": 0})
    second_page = client.get("/admin/api/memories", params={"status": "active", "limit": 2, "offset": 2})

    first_data = first_page.json()
    second_data = second_page.json()

    assert first_page.status_code == 200
    assert second_page.status_code == 200
    assert first_data["total"] == 5
    assert first_data["limit"] == 2
    assert first_data["offset"] == 0
    assert len(first_data["items"]) == 2
    assert second_data["total"] == 5
    assert second_data["limit"] == 2
    assert second_data["offset"] == 2
    assert [item["id"] for item in first_data["items"]] == [5, 4]
    assert [item["id"] for item in second_data["items"]] == [3, 2]


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
            content_text="我正在开发卡咔。",
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
                candidate_memory="用户正在开发卡咔。",
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


def seed_extra_memories(count: int) -> None:
    session_factory = create_session_factory()
    with session_factory() as session:
        user = session.scalar(select(UserRecord))
        scene = session.scalar(select(SceneRecord))
        assert user is not None
        assert scene is not None
        for index in range(count):
            session.add(
                MemoryRecord(
                    user_id=user.id,
                    scene_id=scene.id,
                    memory_text=f"用户分页测试记忆 {index}。",
                    normalized_text=f"用户分页测试记忆 {index}",
                    memory_type="user_fact",
                    confidence=0.8,
                    source_text="测试",
                    source="candidate",
                    status="active",
                    merge_reason="测试",
                    created_at=datetime(2026, 5, 3, 1, 4 + index, tzinfo=timezone.utc),
                    updated_at=datetime(2026, 5, 3, 1, 4 + index, tzinfo=timezone.utc),
                )
            )
        session.commit()
