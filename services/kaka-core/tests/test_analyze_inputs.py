import asyncio
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import importlib.util
import sys

from kaka_core.storage.models import (
    InputRecord,
    MemoryCandidateRecord,
    SceneRecord,
    UserRecord,
    utc_now,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "analyze_inputs.py"


def load_script_module():
    spec = importlib.util.spec_from_file_location("analyze_inputs", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_date_to_utc_range_uses_beijing_time():
    module = load_script_module()

    start, end = module.local_date_to_utc_range(date(2026, 5, 1))

    assert start == datetime(2026, 4, 30, 16, 0, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, 16, 0, tzinfo=timezone.utc)


def test_build_filters():
    module = load_script_module()

    args = module.parse_args_from_list(
        [
            "--group",
            "1073224364",
            "--user",
            "1419825488",
            "--date",
            "2026-05-01",
            "--limit",
            "7",
            "--llm",
            "--mark-skipped",
        ]
    )
    filters = module.build_filters(args)

    assert filters.limit == 7
    assert filters.group_id == "1073224364"
    assert filters.user_id == "1419825488"
    assert filters.target_date == date(2026, 5, 1)
    assert filters.use_llm is True
    assert filters.mark_skipped is True


def test_pycharm_default_args_are_read_only():
    module = load_script_module()

    assert "--write-candidates" not in module.PYCHARM_DEFAULT_ARGS
    assert "--mark-skipped" not in module.PYCHARM_DEFAULT_ARGS
    assert module.PYCHARM_WRITE_CANDIDATES is False
    assert module.PYCHARM_MARK_SKIPPED is False


def test_pycharm_simple_config_builds_input_id_args(monkeypatch):
    module = load_script_module()
    monkeypatch.setattr(module, "PYCHARM_INPUT_IDS", "9,10")
    monkeypatch.setattr(module, "PYCHARM_LIMIT", 30)
    monkeypatch.setattr(module, "PYCHARM_GROUP_ID", "20002")
    monkeypatch.setattr(module, "PYCHARM_USER_ID", "10001")
    monkeypatch.setattr(module, "PYCHARM_DATE", "2026-05-01")
    monkeypatch.setattr(module, "PYCHARM_PRIVATE", False)
    monkeypatch.setattr(module, "PYCHARM_GROUP_CHAT", True)
    monkeypatch.setattr(module, "PYCHARM_LLM", False)
    monkeypatch.setattr(module, "PYCHARM_LLM_BATCH", True)
    monkeypatch.setattr(module, "PYCHARM_WRITE_CANDIDATES", True)
    monkeypatch.setattr(module, "PYCHARM_MARK_SKIPPED", False)

    args = module.parse_args_from_list(module.build_pycharm_simple_args())
    filters = module.build_filters(args)

    assert filters.input_ids == (9, 10)
    assert filters.limit == 30
    assert filters.group_id == "20002"
    assert filters.user_id == "10001"
    assert filters.target_date == date(2026, 5, 1)
    assert filters.scene_type == "group"
    assert filters.use_llm_batch is True
    assert filters.write_candidates is True


def test_build_filters_enables_llm_batch():
    module = load_script_module()

    args = module.parse_args_from_list(["--limit", "20", "--llm-batch"])
    filters = module.build_filters(args)

    assert filters.limit == 20
    assert filters.use_llm_batch is True
    assert filters.use_llm is False


def test_classify_input_text():
    module = load_script_module()

    assert module.classify_input_text("哈哈哈").label == "skipped"
    assert module.classify_input_text("晚上好").label == "skipped"
    assert module.classify_input_text("行吧，烦死了，赶紧关。").label == "skipped"
    assert module.classify_input_text("等下我看看").label == "skipped"
    assert module.classify_input_text("有人吗").label == "skipped"
    assert module.classify_input_text("Yuki给我放一首听听").label == "skipped"
    assert module.classify_input_text("Yuki帮我点一杯奶茶").label == "skipped"
    assert module.classify_input_text("用池宇健的账号").label == "skipped"
    assert module.classify_input_text("我要真实的").label == "not_sure"
    assert module.classify_input_text("我的 API Key 是 xxx").label == "skipped"
    assert module.classify_input_text("我平常对话都能到几千万token").label == "not_sure"
    assert module.classify_input_text("躲进主人哥哥的代码里").label == "not_sure"
    assert module.classify_input_text("用户 @ 了其他人。").label == "skipped"
    assert module.classify_input_text("卡咔").label == "skipped"
    assert module.classify_input_text("at测试2").label == "skipped"
    assert module.classify_input_text("我是大二").label == "candidate"
    assert module.classify_input_text("我是物联网工程专业").label == "candidate"
    assert module.classify_input_text("他是物联网工程专业").label == "candidate"
    assert module.classify_input_text("她是我室友").label == "candidate"
    assert module.classify_input_text("主人哥哥早就给人家换新皮肤了").label == "not_sure"
    assert module.classify_input_text("他喜欢打音游").label == "candidate"
    assert module.classify_input_text("她最近在准备期末考试").label == "candidate"
    assert module.classify_input_text("你以后回答时要解释原因").label == "candidate"
    assert module.classify_input_text("我最近在准备毕设开题").label == "candidate"
    assert module.classify_input_text("晚点我看看").label == "skipped"
    assert module.classify_input_text("这个地方可能还要再讨论一下").label == "not_sure"


def test_infer_rule_memory_type_uses_source_text_to_disambiguate():
    module = load_script_module()

    assert (
        module.infer_rule_memory_type("关系或协作要求", "回复时先给结论。")
        == "stable_preference"
    )
    assert (
        module.infer_rule_memory_type("关系或协作要求", "我更希望你别过度展开。")
        == "stable_preference"
    )
    assert (
        module.infer_rule_memory_type("关系事实", "他是我室友小陈，负责前端。")
        == "relationship_fact"
    )


def test_parse_llm_analysis_reply_candidate():
    module = load_script_module()

    result = module.parse_llm_analysis_reply(
        """
        ```json
        {
          "label": "candidate",
          "memory_type": "stable_preference",
          "confidence": 0.82,
          "reason": "用户明确表达了长期偏好",
          "suggested_memory": "用户希望卡咔解释技术选择背后的原因。"
        }
        ```
        """
    )

    assert result.label == "candidate"
    assert result.memory_type == "stable_preference"
    assert result.confidence == 0.82
    assert result.reason == "用户明确表达了长期偏好"
    assert result.suggested_memory == "用户希望卡咔解释技术选择背后的原因。"


def test_llm_prompts_require_third_person_memory_expression():
    module = load_script_module()

    assert "suggested_memory 必须写成第三人称事实" in module.LLM_ANALYSIS_SYSTEM_PROMPT
    assert "memory 必须写成第三人称事实" in module.LLM_BATCH_ANALYSIS_SYSTEM_PROMPT
    assert "我希望你先给结论" in module.LLM_ANALYSIS_SYSTEM_PROMPT
    assert "该用户希望卡咔先给结论" in module.LLM_ANALYSIS_SYSTEM_PROMPT


def test_normalize_candidate_memory_expression_converts_first_person_prefix():
    module = load_script_module()

    assert module.normalize_candidate_memory_expression("我是物联网工程专业。") == "该用户是物联网工程专业。"
    assert module.normalize_candidate_memory_expression("我的专业是物联网。") == "该用户的专业是物联网。"
    assert module.normalize_candidate_memory_expression("本人喜欢先给结论。") == "该用户喜欢先给结论。"
    assert module.normalize_candidate_memory_expression("用户喜欢简洁回复。") == "用户喜欢简洁回复。"


def test_parse_llm_analysis_reply_invalid_json_is_error():
    module = load_script_module()

    result = module.parse_llm_analysis_reply("不是 JSON")

    assert result.label == "error"
    assert result.memory_type == "none"
    assert result.confidence == 0.0
    assert result.is_error is True


def make_classified_input(
    module,
    input_id: int,
    minutes: int,
    text: str,
    scene_id: str = "20002",
):
    user = UserRecord(
        id=input_id,
        platform="qq",
        platform_user_id=f"1000{input_id}",
        display_name=f"用户{input_id}",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    scene = SceneRecord(
        id=1 if scene_id == "20002" else 2,
        platform="qq",
        scene_type="group",
        scene_id=scene_id,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    input_record = InputRecord(
        id=input_id,
        event_id=f"event-{input_id}",
        user=user,
        scene=scene,
        content_type="text",
        content_text=text,
        raw_event={},
        extra_metadata={},
        analysis_status="not_analyzed",
        created_at=datetime(2026, 5, 2, 12, 0, tzinfo=timezone.utc)
        + timedelta(minutes=minutes),
    )
    return module.ClassifiedInput(
        input_record=input_record,
        user=user,
        scene=scene,
        result=module.classify_input_text(text),
    )


def test_build_llm_batches_groups_by_scene_and_time_window():
    module = load_script_module()
    rows = [
        make_classified_input(module, 1, 0, "这个地方可能还要再讨论一下", "group-a"),
        make_classified_input(module, 2, 3, "我要真实的", "group-a"),
        make_classified_input(module, 3, 11, "这是真的", "group-a"),
        make_classified_input(module, 4, 12, "牛", "group-b"),
    ]

    batches = module.build_llm_batches(rows)

    assert [[item.input_record.id for item in batch.targets] for batch in batches] == [
        [1, 2],
        [3],
        [4],
    ]


def test_select_batch_context_limits_count_and_time_window():
    module = load_script_module()
    scene_rows = [
        make_classified_input(module, 1, -20, "很早之前的话"),
        make_classified_input(module, 2, -9, "前文一"),
        make_classified_input(module, 3, -8, "前文二"),
        make_classified_input(module, 4, 0, "我要真实的"),
        make_classified_input(module, 5, 1, "这是真的"),
        make_classified_input(module, 6, 9, "后文一"),
        make_classified_input(module, 7, 20, "太晚的后文"),
    ]
    targets = [scene_rows[3], scene_rows[4]]

    context = module.select_batch_context(scene_rows, targets)

    assert [item.input_record.id for item in context] == [2, 3, 4, 5, 6]


def test_parse_llm_batch_analysis_reply():
    module = load_script_module()

    parse_result = module.parse_llm_batch_analysis_reply(
        """
        ```json
        [
          {
            "input_id": 4,
            "label": "skipped",
            "memory_type": "none",
            "confidence": 0.91,
            "reason": "上下文显示是临时闲聊",
            "suggested_memory": ""
          },
          {
            "input_id": 5,
            "label": "candidate",
            "memory_type": "user_fact",
            "confidence": 0.8,
            "reason": "用户说明了身份事实",
            "suggested_memory": "用户是物联网工程专业。"
          }
        ]
        ```
        """,
        {4, 5},
    )

    results = parse_result.results
    assert parse_result.parse_failed is False
    assert results[4].label == "skipped"
    assert results[4].suggested_memory == ""
    assert results[5].label == "candidate"
    assert results[5].memory_type == "user_fact"
    assert results[5].suggested_memory == "用户是物联网工程专业。"


def test_parse_llm_batch_analysis_reply_short_keys():
    module = load_script_module()

    parse_result = module.parse_llm_batch_analysis_reply(
        """
        [
          {"id": 4, "label": "skipped", "type": "none", "confidence": 0.9, "reason": "临时闲聊", "memory": ""},
          {"id": 5, "label": "candidate", "type": "stable_preference", "confidence": 0.8, "reason": "稳定偏好", "memory": "用户希望回答简洁。"}
        ]
        """,
        {4, 5},
    )

    results = parse_result.results
    assert parse_result.parse_failed is False
    assert results[4].label == "skipped"
    assert results[4].memory_type == "none"
    assert results[5].label == "candidate"
    assert results[5].memory_type == "stable_preference"
    assert results[5].suggested_memory == "用户希望回答简洁。"


def test_parse_llm_batch_analysis_reply_invalid_json_requests_retry():
    module = load_script_module()

    parse_result = module.parse_llm_batch_analysis_reply("不是 JSON", {4, 5})

    assert parse_result.results == {}
    assert parse_result.parse_failed is True
    assert "有效 JSON 数组" in parse_result.error


def test_analyze_batch_with_llm_retry_splits_failed_batch():
    module = load_script_module()
    rows = [
        make_classified_input(module, 1, 0, "我要真实的"),
        make_classified_input(module, 2, 1, "这是真的"),
    ]
    batch = module.LLMAnalysisBatch(targets=rows, context_rows=rows)

    class FakeRouter:
        def __init__(self):
            self.replies = [
                "不是 JSON",
                '[{"id": 1, "label": "skipped", "type": "none", "confidence": 0.7, "reason": "上下文不足", "memory": ""}]',
                '[{"id": 2, "label": "candidate", "type": "user_fact", "confidence": 0.8, "reason": "明确事实", "memory": "用户确认这是真的。"}]',
            ]
            self.calls = 0

        async def summarize_memory(self, _messages):
            reply = self.replies[self.calls]
            self.calls += 1
            return reply

    router = FakeRouter()
    stats = module.BatchLLMStats(initial_batch_count=1, target_count=2)
    results = asyncio.run(module.analyze_batch_with_llm_retry(batch, router, stats))

    assert router.calls == 3
    assert stats.request_count == 3
    assert stats.retry_request_count == 2
    assert stats.parse_failure_count == 1
    assert stats.split_retry_count == 1
    assert results[1].label == "skipped"
    assert results[2].label == "candidate"
    assert results[2].suggested_memory == "用户确认这是真的。"


def test_format_batch_plan_shows_package_details():
    module = load_script_module()
    rows = [
        make_classified_input(module, 1, -2, "哈哈哈"),
        make_classified_input(module, 2, 0, "我要真实的"),
        make_classified_input(module, 3, 1, "这是真的"),
        make_classified_input(module, 4, 2, "我是大二"),
    ]
    batches = module.build_llm_batches(rows)

    text = module.format_batch_plan(rows, batches, can_call_llm=True)

    assert "批量 LLM 分析计划" in text
    assert "模型初始包数：1" in text
    assert "预计最低请求次数：1" in text
    assert "包 #1" in text
    assert "目标 input_id：2, 3" in text
    assert "上下文 input_id：1, 4" in text
    assert "发送内容：" in text
    assert "[CTX] #1" in text
    assert "[TARGET] #2" in text


def test_format_batch_execution_summary():
    module = load_script_module()
    stats = module.BatchLLMStats(
        initial_batch_count=1,
        target_count=2,
        request_count=3,
        parse_failure_count=1,
        split_retry_count=1,
        api_error_count=0,
        missing_result_count=1,
    )
    results = {
        1: module.LLMAnalysisResult(
            label="skipped",
            memory_type="none",
            confidence=0.7,
            reason="上下文不足",
        ),
        2: module.LLMAnalysisResult(
            label="error",
            memory_type="none",
            confidence=0.0,
            reason="LLM 未返回此 input_id 的结果",
            error="missing input_id=2",
        ),
    }

    text = module.format_batch_execution_summary(stats, results)

    assert "批量 LLM 执行结果" in text
    assert "初始包数：1" in text
    assert "实际请求次数：3" in text
    assert "自动拆包重试：1 次" in text
    assert "重试新增请求：2 次" in text
    assert "解析失败触发：1 次" in text
    assert "模型漏返结果：1 条" in text
    assert "最终结果：candidate=0 / skipped=1 / error=1" in text


def test_format_analysis_with_llm_result():
    module = load_script_module()
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
    input_record = InputRecord(
        event_id="input-1",
        user=user,
        scene=scene,
        content_type="text",
        content_text="我希望你以后解释原因",
        raw_event={},
        extra_metadata={},
        analysis_status="not_analyzed",
        created_at=utc_now(),
    )
    rule_result = module.AnalysisResult("not_sure", "普通聊天，后续可接入更细分析")
    llm_result = module.LLMAnalysisResult(
        label="candidate",
        memory_type="stable_preference",
        confidence=0.8,
        reason="用户表达了稳定偏好",
        suggested_memory="用户希望卡咔解释技术选择背后的原因。",
    )

    text = module.format_analysis(1, input_record, user, scene, rule_result, llm_result)

    assert "规则结果：not_sure / 普通聊天，后续可接入更细分析" in text
    assert "LLM建议：candidate" in text
    assert "记忆类型：stable_preference" in text
    assert "建议记忆：用户希望卡咔解释技术选择背后的原因。" in text


def test_mark_skipped_updates_only_skipped_rows():
    module = load_script_module()
    engine = create_engine("sqlite:///:memory:")
    module.InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

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
        skipped = InputRecord(
            event_id="skip-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="哈哈哈",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        candidate = InputRecord(
            event_id="candidate-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="我是物联网工程专业",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        session.add_all([skipped, candidate])
        session.commit()

        filters = module.AnalysisFilters(limit=10, mark_skipped=True)
        rows = module.load_unanalyzed_inputs(session, filters)
        for input_record, _user, _scene in rows:
            result = module.classify_input_text(input_record.content_text)
            if result.can_mark_skipped:
                input_record.analysis_status = module.ANALYSIS_STATUS_SKIPPED
        session.commit()

        statuses = {
            row.event_id: row.analysis_status
            for row in session.scalars(select(InputRecord)).all()
        }

    assert statuses == {
        "skip-1": "skipped",
        "candidate-1": "not_analyzed",
    }


def test_write_candidates_marks_inputs_and_deduplicates():
    module = load_script_module()
    engine = create_engine("sqlite:///:memory:")
    module.InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

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
        skipped = InputRecord(
            event_id="skip-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="哈哈哈",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        rule_candidate = InputRecord(
            event_id="rule-candidate-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="我是物联网工程专业",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        llm_candidate = InputRecord(
            event_id="llm-candidate-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="这个地方可能还要再讨论一下",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        llm_skipped = InputRecord(
            event_id="llm-skipped-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="我要真实的",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        llm_error = InputRecord(
            event_id="llm-error-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="这是真的",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        session.add_all([skipped, rule_candidate, llm_candidate, llm_skipped, llm_error])
        session.commit()

        rows = module.load_unanalyzed_inputs(session, module.AnalysisFilters(limit=10))
        classified_rows = module.classify_rows(rows)
        batch_results = {
            llm_candidate.id: module.LLMAnalysisResult(
                label="candidate",
                memory_type="important_event",
                confidence=0.82,
                reason="可能是项目事项",
                suggested_memory="用户可能需要继续讨论这个地方。",
            ),
            llm_skipped.id: module.LLMAnalysisResult(
                label="skipped",
                memory_type="none",
                confidence=0.7,
                reason="上下文不足",
            ),
            llm_error.id: module.LLMAnalysisResult(
                label="error",
                memory_type="none",
                confidence=0.0,
                reason="LLM 调用失败",
                error="boom",
            ),
        }

        stats = module.write_candidates_and_mark_inputs(
            session,
            classified_rows,
            batch_results,
            analysis_model="deepseek-v4-flash",
            analysis_prompt_version="test-prompt",
        )
        session.commit()
        stats_again = module.write_candidates_and_mark_inputs(
            session,
            classified_rows,
            batch_results,
            analysis_model="deepseek-v4-flash",
            analysis_prompt_version="test-prompt",
        )
        session.commit()

        statuses = {
            row.event_id: row.analysis_status
            for row in session.scalars(select(InputRecord)).all()
        }
        candidates = session.scalars(select(MemoryCandidateRecord)).all()
        memories = {candidate.source_input.event_id: candidate for candidate in candidates}

    assert stats.rule_skipped_marked == 1
    assert stats.rule_candidates_inserted == 1
    assert stats.llm_candidates_inserted == 1
    assert stats.llm_skipped_marked == 1
    assert stats.llm_errors_left_unprocessed == 1
    assert stats_again.existing_candidates == 2
    assert len(candidates) == 2
    assert statuses == {
        "skip-1": "skipped",
        "rule-candidate-1": "analyzed",
        "llm-candidate-1": "analyzed",
        "llm-skipped-1": "skipped",
        "llm-error-1": "not_analyzed",
    }
    assert memories["rule-candidate-1"].analysis_model == "rule"
    assert memories["rule-candidate-1"].candidate_memory == "该用户是物联网工程专业"
    assert memories["llm-candidate-1"].analysis_model == "deepseek-v4-flash"
    assert memories["llm-candidate-1"].candidate_memory == "用户可能需要继续讨论这个地方。"


def test_repeated_llm_errors_eventually_mark_input_failed():
    """LLM 反复失败的 input 累计到重试上限后落到 analysis_failed，不再无限重投。"""

    module = load_script_module()
    engine = create_engine("sqlite:///:memory:")
    module.InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

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
        llm_error = InputRecord(
            event_id="llm-error-retry",
            user=user,
            scene=scene,
            content_type="text",
            content_text="这是真的",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        session.add(llm_error)
        session.commit()

        rows = module.load_unanalyzed_inputs(session, module.AnalysisFilters(limit=10))
        classified_rows = module.classify_rows(rows)
        batch_results = {
            llm_error.id: module.LLMAnalysisResult(
                label="error",
                memory_type="none",
                confidence=0.0,
                reason="LLM 调用失败",
                error="boom",
            ),
        }

        # 前 ANALYSIS_MAX_RETRIES - 1 次失败后仍保持 not_analyzed，可继续重试。
        for _ in range(module.ANALYSIS_MAX_RETRIES - 1):
            module.write_candidates_and_mark_inputs(
                session,
                classified_rows,
                batch_results,
                analysis_model="deepseek-v4-flash",
                analysis_prompt_version="test-prompt",
            )
            session.commit()
            session.refresh(llm_error)
            assert llm_error.analysis_status == "not_analyzed"

        # 达到上限的这次失败把 input 落到终态 analysis_failed。
        stats = module.write_candidates_and_mark_inputs(
            session,
            classified_rows,
            batch_results,
            analysis_model="deepseek-v4-flash",
            analysis_prompt_version="test-prompt",
        )
        session.commit()
        session.refresh(llm_error)

    assert stats.failed_marked == 1
    assert llm_error.analysis_status == module.ANALYSIS_STATUS_FAILED
    assert llm_error.extra_metadata[module.ANALYSIS_RETRY_METADATA_KEY] == module.ANALYSIS_MAX_RETRIES


def test_one_input_can_keep_multiple_distinct_candidates():
    module = load_script_module()
    engine = create_engine("sqlite:///:memory:")
    module.InputRecord.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

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
        input_record = InputRecord(
            event_id="multi-candidate-1",
            user=user,
            scene=scene,
            content_type="text",
            content_text="我是物联网工程专业，我喜欢先给结论。",
            raw_event={},
            extra_metadata={},
            analysis_status="not_analyzed",
            created_at=utc_now(),
        )
        session.add(input_record)
        session.flush()

        item = module.ClassifiedInput(
            input_record=input_record,
            user=user,
            scene=scene,
            result=module.AnalysisResult("candidate", "测试"),
        )
        keys = module.load_existing_candidate_keys(session, [item])
        first = module.add_memory_candidate_if_missing(
            session,
            item,
            memory_text="该用户是物联网工程专业。",
            memory_type="user_fact",
            confidence=0.8,
            reason="身份事实",
            analysis_model="test",
            analysis_prompt_version="test",
            existing_candidate_keys=keys,
        )
        second = module.add_memory_candidate_if_missing(
            session,
            item,
            memory_text="该用户喜欢先给结论。",
            memory_type="stable_preference",
            confidence=0.8,
            reason="稳定偏好",
            analysis_model="test",
            analysis_prompt_version="test",
            existing_candidate_keys=keys,
        )
        duplicate = module.add_memory_candidate_if_missing(
            session,
            item,
            memory_text="该用户喜欢先给结论。",
            memory_type="stable_preference",
            confidence=0.8,
            reason="稳定偏好",
            analysis_model="test",
            analysis_prompt_version="test",
            existing_candidate_keys=keys,
        )
        session.commit()

        candidates = session.scalars(select(MemoryCandidateRecord)).all()

    assert first is True
    assert second is True
    assert duplicate is False
    assert len(candidates) == 2
