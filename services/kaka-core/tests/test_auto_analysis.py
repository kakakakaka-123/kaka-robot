from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from kaka_core.config.settings import MemoryAnalysisSettings
from kaka_core.memory import auto_analysis
from kaka_core.memory import auto_jobs
from kaka_core.storage.models import AutoJobRunRecord, Base, InputRecord, SceneRecord, UserRecord, utc_now


def test_seconds_until_next_hour():
    now = datetime(2026, 5, 2, 14, 37, 30, tzinfo=timezone.utc)

    assert auto_analysis.seconds_until_next_hour(now) == 1350


def test_next_check_delay_uses_interval_when_configured():
    now = datetime(2026, 5, 2, 14, 37, 30, tzinfo=timezone.utc)

    assert (
        auto_analysis.next_check_delay(
            MemoryAnalysisSettings(
                enabled=True,
                trigger_count=5,
                batch_limit=5,
                max_runs_per_check=1,
                interval_seconds=60,
            ),
            now,
        )
        == 60
    )


def test_next_check_delay_falls_back_to_next_hour():
    now = datetime(2026, 5, 2, 14, 37, 30, tzinfo=timezone.utc)

    assert (
        auto_analysis.next_check_delay(
            MemoryAnalysisSettings(
                enabled=True,
                trigger_count=50,
                batch_limit=50,
                max_runs_per_check=2,
                interval_seconds=0,
            ),
            now,
        )
        == 1350
    )


@pytest.mark.anyio
async def test_auto_analysis_skips_below_threshold(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed_inputs(session_factory, 49)

    monkeypatch.setattr(auto_analysis, "init_database", lambda: None)
    monkeypatch.setattr(auto_analysis, "create_session_factory", lambda: session_factory)
    monkeypatch.setattr(auto_jobs, "init_database", lambda: None)
    monkeypatch.setattr(auto_jobs, "create_session_factory", lambda: session_factory)

    summary = await auto_analysis.run_auto_analysis_check(
        MemoryAnalysisSettings(
            enabled=True,
            trigger_count=50,
            batch_limit=50,
            max_runs_per_check=2,
            interval_seconds=0,
        )
    )

    assert summary.ran is False
    assert summary.checked_count == 49
    assert "未达到触发门槛" in summary.reason


@pytest.mark.anyio
async def test_auto_analysis_force_ignores_threshold(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed_inputs(session_factory, 3)

    class FakeAnalyzeInputs:
        LLM_BATCH_ANALYSIS_PROMPT_VERSION = "test-prompt"

        class AnalysisFilters:
            def __init__(self, *, limit, use_llm_batch, write_candidates):
                self.limit = limit
                self.use_llm_batch = use_llm_batch
                self.write_candidates = write_candidates
                self.user_id = None
                self.group_id = None
                self.scene_type = None
                self.target_date = None

        class BatchLLMStats:
            pass

        @staticmethod
        def load_unanalyzed_inputs(session, filters):
            return list(
                session.query(InputRecord, UserRecord, SceneRecord)
                .join(UserRecord, InputRecord.user_id == UserRecord.id)
                .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
                .filter(InputRecord.analysis_status == "not_analyzed")
                .order_by(InputRecord.id)
                .limit(filters.limit)
                .all()
            )

        @staticmethod
        def classify_rows(rows):
            return rows

        @staticmethod
        def build_llm_batches(classified_rows):
            return [classified_rows] if classified_rows else []

        @staticmethod
        async def analyze_llm_batches(_batches, _router, _batch_stats):
            return {}

        @staticmethod
        def write_candidates_and_mark_inputs(session, classified_rows, _batch_results, **_kwargs):
            for input_record, _user, _scene in classified_rows:
                input_record.analysis_status = "skipped"
            return SimpleNamespace(
                total_candidates_inserted=0,
                total_skipped_marked=len(classified_rows),
                analyzed_marked=0,
                llm_errors_left_unprocessed=0,
                missing_llm_results=0,
                failed_marked=0,
            )

    monkeypatch.setattr(auto_analysis, "init_database", lambda: None)
    monkeypatch.setattr(auto_analysis, "create_session_factory", lambda: session_factory)
    monkeypatch.setattr(auto_analysis, "load_analyze_inputs_module", lambda: FakeAnalyzeInputs)
    monkeypatch.setattr(auto_analysis, "LLMRouter", lambda _settings: object())
    monkeypatch.setattr(
        auto_analysis,
        "get_settings",
        lambda: SimpleNamespace(
            llm=SimpleNamespace(
                can_call_remote=True,
                memory_model="test-memory-model",
            )
        ),
    )

    summary = await auto_analysis.run_auto_analysis_check(
        MemoryAnalysisSettings(
            enabled=True,
            trigger_count=50,
            batch_limit=50,
            max_runs_per_check=2,
            interval_seconds=0,
        ),
        force=True,
    )

    with session_factory() as session:
        remaining = auto_analysis.count_not_analyzed_inputs(session)

    assert summary.ran is True
    assert summary.reason == "手动触发执行"
    assert summary.checked_count == 3
    assert summary.processed_runs == 1
    assert summary.skipped_marked == 3
    assert remaining == 0


@pytest.mark.anyio
async def test_auto_analysis_check_and_record_writes_skipped_run(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed_inputs(session_factory, 3)

    monkeypatch.setattr(auto_analysis, "init_database", lambda: None)
    monkeypatch.setattr(auto_analysis, "create_session_factory", lambda: session_factory)
    monkeypatch.setattr(auto_jobs, "init_database", lambda: None)
    monkeypatch.setattr(auto_jobs, "create_session_factory", lambda: session_factory)

    summary = await auto_analysis.run_auto_analysis_check_and_record(
        MemoryAnalysisSettings(
            enabled=True,
            trigger_count=50,
            batch_limit=50,
            max_runs_per_check=2,
            interval_seconds=0,
        )
    )

    with session_factory() as session:
        run = session.scalar(select(AutoJobRunRecord))

    assert summary.ran is False
    assert run is not None
    assert run.job_name == "auto_analysis"
    assert run.status == "skipped"
    assert run.checked_count == 3
    assert run.processed_runs == 0


@pytest.mark.anyio
async def test_auto_analysis_check_and_record_skips_when_job_lock_is_held(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(auto_analysis, "init_database", lambda: None)
    monkeypatch.setattr(auto_analysis, "create_session_factory", lambda: session_factory)
    monkeypatch.setattr(auto_jobs, "init_database", lambda: None)
    monkeypatch.setattr(auto_jobs, "create_session_factory", lambda: session_factory)

    owner_token, lock_error = auto_jobs.acquire_auto_job_lock_safely(
        auto_analysis.AUTO_ANALYSIS_JOB_NAME
    )
    assert owner_token is not None
    assert lock_error is None

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("auto analysis should not run while the cross-process lock is held")

    monkeypatch.setattr(auto_analysis, "run_auto_analysis_check", fail_if_called)

    summary = await auto_analysis.run_auto_analysis_check_and_record(
        MemoryAnalysisSettings(
            enabled=True,
            trigger_count=50,
            batch_limit=50,
            max_runs_per_check=2,
            interval_seconds=0,
        )
    )

    with session_factory() as session:
        run = session.scalar(select(AutoJobRunRecord))

    assert summary.ran is False
    assert summary.reason == "已有同名自动任务在运行"
    assert run is not None
    assert run.job_name == "auto_analysis"
    assert run.status == "skipped"


@pytest.mark.anyio
async def test_auto_analysis_runs_at_most_two_batches(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    seed_inputs(session_factory, 120)

    class FakeAnalyzeInputs:
        LLM_BATCH_ANALYSIS_PROMPT_VERSION = "test-prompt"

        class AnalysisFilters:
            def __init__(self, *, limit, use_llm_batch, write_candidates):
                self.limit = limit
                self.use_llm_batch = use_llm_batch
                self.write_candidates = write_candidates
                self.user_id = None
                self.group_id = None
                self.scene_type = None
                self.target_date = None

        class BatchLLMStats:
            pass

        @staticmethod
        def load_unanalyzed_inputs(session, filters):
            return list(
                session.query(InputRecord, UserRecord, SceneRecord)
                .join(UserRecord, InputRecord.user_id == UserRecord.id)
                .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
                .filter(InputRecord.analysis_status == "not_analyzed")
                .order_by(InputRecord.id)
                .limit(filters.limit)
                .all()
            )

        @staticmethod
        def classify_rows(rows):
            return rows

        @staticmethod
        def build_llm_batches(classified_rows):
            return [classified_rows] if classified_rows else []

        @staticmethod
        async def analyze_llm_batches(_batches, _router, _batch_stats):
            return {}

        @staticmethod
        def write_candidates_and_mark_inputs(session, classified_rows, _batch_results, **_kwargs):
            for input_record, _user, _scene in classified_rows:
                input_record.analysis_status = "skipped"
            return SimpleNamespace(
                total_candidates_inserted=0,
                total_skipped_marked=len(classified_rows),
                analyzed_marked=0,
                llm_errors_left_unprocessed=0,
                missing_llm_results=0,
                failed_marked=0,
            )

    monkeypatch.setattr(auto_analysis, "init_database", lambda: None)
    monkeypatch.setattr(auto_analysis, "create_session_factory", lambda: session_factory)
    monkeypatch.setattr(auto_analysis, "load_analyze_inputs_module", lambda: FakeAnalyzeInputs)
    monkeypatch.setattr(auto_analysis, "LLMRouter", lambda _settings: object())
    monkeypatch.setattr(
        auto_analysis,
        "get_settings",
        lambda: SimpleNamespace(
            llm=SimpleNamespace(
                can_call_remote=True,
                memory_model="test-memory-model",
            )
        ),
    )

    summary = await auto_analysis.run_auto_analysis_check(
        MemoryAnalysisSettings(
            enabled=True,
            trigger_count=50,
            batch_limit=50,
            max_runs_per_check=2,
            interval_seconds=0,
        )
    )

    with session_factory() as session:
        remaining = auto_analysis.count_not_analyzed_inputs(session)

    assert summary.ran is True
    assert summary.processed_runs == 2
    assert summary.skipped_marked == 100
    assert remaining == 20


def seed_inputs(session_factory, count: int) -> None:
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
        for index in range(count):
            session.add(
                InputRecord(
                    event_id=f"input-{index}",
                    user=user,
                    scene=scene,
                    content_type="text",
                    content_text=f"消息 {index}",
                    raw_event={},
                    extra_metadata={},
                    analysis_status="not_analyzed",
                    created_at=utc_now(),
                )
            )
        session.commit()
