"""分析未处理的输入记录。

这是长期记忆和用户画像之前的最小分析工具。默认不调用大模型，
不写入 memories 表，只用保守规则把 inputs 里的消息分成几类：

    python services/kaka-core/scripts/analyze_inputs.py
    python services/kaka-core/scripts/analyze_inputs.py --limit 50
    python services/kaka-core/scripts/analyze_inputs.py --group 1073224364
    python services/kaka-core/scripts/analyze_inputs.py --user 1419825488
    python services/kaka-core/scripts/analyze_inputs.py --date 2026-05-01
    python services/kaka-core/scripts/analyze_inputs.py --llm
    python services/kaka-core/scripts/analyze_inputs.py --llm-batch
    python services/kaka-core/scripts/analyze_inputs.py --llm-batch --write-candidates
    python services/kaka-core/scripts/analyze_inputs.py --mark-skipped

默认只打印结果，不修改数据库。
只有加上 --llm 时，才会把规则判断为 not_sure 的文本发送给大模型做只读判断。
只有加上 --llm-batch 时，才会把 not_sure 按场景和时间打包发给大模型做只读判断。
只有加上 --write-candidates 时，才会写入 memory_candidates，并标记已处理 input。
只有加上 --mark-skipped 时，才会把明显无价值的记录标记为 skipped。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "kaka-core" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaka_core.storage.database import create_session_factory, init_database  # noqa: E402
from kaka_core.storage.models import (  # noqa: E402
    InputRecord,
    MemoryCandidateRecord,
    SceneRecord,
    UserRecord,
)
from kaka_core.config.settings import get_settings  # noqa: E402
from kaka_core.llm.client import ChatMessage, LLMClientError  # noqa: E402
from kaka_core.llm.router import LLMRouter  # noqa: E402

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

# PyCharm 右键运行时可以直接改这里，不需要去找 Parameters。
#
# 可用关键词：
# --limit N              分析最近 N 条未分析记录，默认 20。
# --group 群号           只看某个 QQ 群。
# --user QQ号            只看某个 QQ 用户。
# --date YYYY-MM-DD      只看某一天，按北京时间理解。
# --private              只看私聊。
# --group-chat           只看群聊。
# --llm                  只读调用大模型：只分析规则判断为 not_sure 的记录。
# --llm-batch            只读批量调用大模型：把 not_sure 按场景和时间打包分析。
# --write-candidates     会修改数据库：写入候选区，并标记 analyzed/skipped。
# --mark-skipped         会修改数据库：把 skipped 记录标记为 analysis_status=skipped。
#
# 分类含义：
# skipped                明显无价值或占位消息，例如寒暄、测试消息、@ 占位。
# candidate              可能值得后续进入候选记忆，例如身份、偏好、项目长期信息。
# not_sure               普通聊天或上下文不足，暂时不自动跳过。
#
# PyCharm 简单模式：只改这里，再右键运行脚本。
# 默认只读预览，不调用 LLM，不写数据库。
# 已经在数据库可视化软件里看到 inputs.id 时，可以填 PYCHARM_INPUT_IDS。
PYCHARM_INPUT_IDS = ""
PYCHARM_LIMIT = 30
PYCHARM_GROUP_ID = ""
PYCHARM_USER_ID = ""
PYCHARM_DATE = ""
PYCHARM_PRIVATE = False
PYCHARM_GROUP_CHAT = False
PYCHARM_LLM = False
PYCHARM_LLM_BATCH = False

# 写库开关，默认关闭。PYCHARM_WRITE_CANDIDATES 必须配合 PYCHARM_LLM_BATCH=True。
PYCHARM_WRITE_CANDIDATES = False
PYCHARM_MARK_SKIPPED = False

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []

ANALYSIS_STATUS_NOT_ANALYZED = "not_analyzed"
ANALYSIS_STATUS_SKIPPED = "skipped"
ANALYSIS_STATUS_ANALYZED = "analyzed"
MEMORY_CANDIDATE_STATUS_PENDING = "pending"
RULE_ANALYSIS_MODEL = "rule"
RULE_ANALYSIS_PROMPT_VERSION = "rule-candidate-v2"
LLM_BATCH_ANALYSIS_PROMPT_VERSION = "llm-batch-memory-candidate-v3"

BATCH_NOT_SURE_SIZE = 10
BATCH_MAX_SPAN = timedelta(minutes=10)
BATCH_CONTEXT_BEFORE_COUNT = 5
BATCH_CONTEXT_AFTER_COUNT = 5
BATCH_CONTEXT_TIME_WINDOW = timedelta(minutes=10)

SKIP_EXACT_TEXTS = {
    "用户 @ 了卡咔。",
    "用户 @ 了其他人。",
    "非文本消息或 @ 其他人。",
}

COMMON_LOW_VALUE_TEXTS = {
    "1",
    "6",
    "嗯",
    "嗯嗯",
    "啊",
    "昂",
    "哦",
    "噢",
    "好",
    "好啊",
    "好吧",
    "好的",
    "行",
    "行吧",
    "可以",
    "可",
    "也行",
    "都行",
    "没事",
    "没啥",
    "没什么",
    "算了",
    "随便",
    "无所谓",
    "对",
    "对啊",
    "对的",
    "是",
    "是的",
    "不是",
    "不是的",
    "确实",
    "雀食",
    "还行",
    "还好",
    "不知道",
    "不清楚",
    "不懂",
    "懂了",
    "知道了",
    "了解",
    "收到",
    "ok",
    "okk",
    "哈哈",
    "哈哈哈",
    "笑死",
    "草",
    "乐",
    "乐了",
    "绷",
    "绷不住了",
    "绝了",
    "早",
    "早安",
    "午安",
    "晚安",
    "拜拜",
    "再见",
    "睡了",
    "溜了",
    "来了",
    "在",
    "在的",
    "谢谢",
    "谢了",
    "卡咔",
}

CANDIDATE_PATTERNS = [
    (
        "身份信息",
        re.compile(
            r"(我是|我叫|叫我|我的名字|我的昵称|称呼我|本人|"
            r"他是|她是|ta是|TA是|这个人是|那个人是|群主是|管理员是|"
            r"他叫|她叫|ta叫|TA叫|他的名字|她的名字|他的昵称|她的昵称|"
            r"专业|学校|学院|年级|大一|大二|大三|大四|本科|研究生|学生|老师|"
            r"工作|职业|实习|上班|公司|同学|朋友|室友|舍友|群主|管理员)"
        ),
    ),
    (
        "稳定偏好",
        re.compile(
            r"(我喜欢|我不喜欢|我更喜欢|我最喜欢|我希望|我不希望|我习惯|我讨厌|"
            r"我一般|我通常|我经常|"
            r"他喜欢|她喜欢|ta喜欢|TA喜欢|他不喜欢|她不喜欢|他讨厌|她讨厌|"
            r"他习惯|她习惯|他一般|她一般|他经常|她经常|"
            r"偏好|以后都|之后都|别叫我|不要叫我|可以叫我)"
        ),
    ),
    (
        "项目长期信息",
        re.compile(
            r"(项目|卡咔 v2|机器人|数据库|文档|PyCharm|命令行|开发日志|表结构|长期记忆|"
            r"用户画像|DeepSeek|LLM|NoneBot|FastAPI|SQLite|记忆候选|"
            r"毕设|毕业设计|AIoT|物联网|开题)"
        ),
    ),
    (
        "明确记忆请求",
        re.compile(r"(记住|别忘|以后记得|你要记得|帮我记|替我记|你记一下|这个要记)"),
    ),
    (
        "关系或协作要求",
        re.compile(
            r"(你以后|你要|你别|你不要|回答时|回复时|说话方式|语气|风格|"
            r"不要.*卖萌|解释.*原因|先.*说明|别.*装)"
        ),
    ),
    (
        "长期计划或重要节点",
        re.compile(
            r"(我打算|我计划|我准备|我正在|我最近在(做|学|准备|开发|写|看|研究)|"
            r"他打算|她打算|他计划|她计划|他准备|她准备|他正在|她正在|"
            r"他最近在(做|学|准备|开发|写|看|研究)|她最近在(做|学|准备|开发|写|看|研究)|"
            r"长期|目标|路线|"
            r"考试|期末|课程|作业|论文|毕设|开题|实习|面试|比赛|项目节点|DDL|截止|生日)"
        ),
    ),
    (
        "关系事实",
        re.compile(
            r"(他是我|她是我|ta是我|TA是我|我是他|我是她|"
            r"他是我的|她是我的|ta是我的|TA是我的|"
            r"朋友|同学|室友|舍友|对象|男朋友|女朋友|兄弟|亲友|熟人|维护者)"
        ),
    ),
]

SENSITIVE_PATTERNS = [
    (
        "敏感信息，不进入记忆",
        re.compile(
            r"(密码|口令|api[\s_-]*key|apikey|密钥|secret|\btoken\b|access[\s_-]*token|"
            r"refresh[\s_-]*token|身份证|银行卡|住址|家庭住址)",
            re.IGNORECASE,
        ),
    ),
]

LOW_VALUE_PATTERNS = [
    (
        "常见笑声或刷屏回应",
        re.compile(r"^(哈+|h+h+|233+|6+|草+|笑死了?|绷不住了?|乐了?|绝了)+[。！!？?~～…]*$", re.IGNORECASE),
    ),
    (
        "常见语气词",
        re.compile(r"^(啊+|哦+|噢+|诶+|欸+|呃+|额+|唉+|哎+|啧+|em+|emm+|emmm+)[。！!？?~～…]*$", re.IGNORECASE),
    ),
    (
        "常见问候或告别",
        re.compile(
            r"^(早上好|中午好|下午好|晚上好|晚好|你好|嗨|hello|hi|拜拜|再见|晚安|睡了|溜了|下了)"
            r"[。！!？?~～…]*$",
            re.IGNORECASE,
        ),
    ),
    (
        "常见即时问句",
        re.compile(r"(在吗|你在吗|有人吗|干嘛呢|吃了吗|睡了吗|几点了|今天吃啥|吃什么|玩什么|有空吗)"),
    ),
    (
        "短促态度回应",
        re.compile(r"^(行吧|好吧|可以吧|没事吧|随便吧|都行|也行|先这样|差不多)[。！!？?~～…]*$"),
    ),
    (
        "临时情绪宣泄",
        re.compile(r"(烦死了|无语|服了|麻了|崩溃|裂开|救命|累死了|困死了|气死了|寄了|完了|炸了)"),
    ),
    (
        "临时娱乐或点歌指令",
        re.compile(r"(点歌|放歌|来一首|放一首|听歌|音乐软件|听不了|别放歌|播放音乐|切歌|下一首)"),
    ),
    (
        "临时点单或跑腿指令",
        re.compile(r"(点一杯|点杯|奶茶|外卖|帮我买|帮我点|给我点|请我喝|哪有钱给你点)"),
    ),
    (
        "临时账号操作",
        re.compile(r"(登.*号|登录.*号|用.*的号|用.*的账号)"),
    ),
    (
        "临时身体不适或环境抱怨",
        re.compile(r"(吵得|吵死|脑壳疼|头疼|头痛|太吵|好吵|难受死了)"),
    ),
    (
        "临时动作或即时安排",
        re.compile(r"^(等下|等会|稍等|马上|晚点|回头|一会儿|一会|先这样|先不说).{0,12}$"),
    ),
    (
        "短期操作指令或结束语",
        re.compile(r"^(我看看|我去看看|算了|别管|关了|开了|赶紧关|睡觉了|吃饭了|下线了)[。！!？?~～…]*$"),
    ),
    (
        "纯媒体或占位描述",
        re.compile(r"^(\[.*\]|【.*】|表情|图片|语音|文件|视频)$", re.IGNORECASE),
    ),
]

PUNCTUATION_RE = re.compile(r"^[\s\W_]+$", re.UNICODE)

LLM_ANALYSIS_SYSTEM_PROMPT = """你是卡咔 v2 的长期记忆候选分析器。
你的任务是判断一条聊天输入是否值得进入长期记忆候选区。

只允许输出 JSON，不要输出 Markdown，不要解释 JSON 之外的内容。

判断原则：
- 只把长期有用、来源明确、后续对话可能用得上的信息判断为 candidate。
- 普通寒暄、玩笑、临时情绪、上下文不足、单次闲聊都判断为 skipped。
- 不确定就判断为 skipped，宁可漏掉，也不要乱记。
- 不保存 API Key、密码、Token、住址、身份证、银行卡等高敏感隐私。
- 不把模型猜测当事实，不把群友隐私随便变成记忆。
- suggested_memory 必须写成第三人称事实，不要保留“我是...”“我喜欢...”这类第一人称原话。
- 如果消息中的“我 / 我的 / 本人”指发送者，应改写为“该用户 / 用户”；如果“你”指卡咔，应改写为“卡咔”。
- 示例：“我是物联网工程专业”应写为“该用户是物联网工程专业。”；“我希望你先给结论”应写为“该用户希望卡咔先给结论。”

JSON 字段：
{
  "label": "candidate 或 skipped",
  "memory_type": "user_fact / relationship_fact / important_event / stable_preference / none",
  "confidence": 0.0 到 1.0,
  "reason": "一句中文理由",
  "suggested_memory": "建议写入候选区的中文记忆；如果 label=skipped，填空字符串"
}
"""

LLM_BATCH_ANALYSIS_SYSTEM_PROMPT = """你是卡咔 v2 的长期记忆候选批量分析器。
你的任务是根据同一场景的一小段聊天，判断其中 target=true 的输入是否值得进入长期记忆候选区。

只允许输出 JSON 数组，不要输出 Markdown，不要解释 JSON 之外的内容。
输出必须尽量短，reason 不超过 20 个中文字符。

判断原则：
- 只判断 target=true 的消息；target=false 的消息只作为上下文参考，不要为它们输出结果。
- 候选区不是正式记忆；对来源明确、后续可能有用的信息，可以进入 candidate 供人工审核。
- 用户对卡咔项目作出的设计决策、流程规则、表字段语义、状态含义、模型选择、自动任务配置、审核策略、安全策略，应判断为 candidate。
- 用户稳定偏好、回复风格要求、工具使用习惯、测试/运行方式、对候选区查看方式的要求，应判断为 candidate。
- 任务节点、截止时间、当前进度、重要计划、模型或配置的纠错更新，应判断为 candidate。
- 多用户群聊中，某人清楚说明自己的职责、关系、偏好或分工时，应判断为 candidate，并在 memory 中写清楚是谁。
- target 短句如果能从相邻上下文补全含义，应按补全后的含义判断，不要只因短或省略就跳过。
- 否定和纠错类消息如果是在更新旧信息，应保留当前有效结论，例如“不用 X，改用 Y”。
- 普通寒暄、玩笑、角色扮演、临时情绪、随口评价、无明确对象的指代、一次性动作、吃饭睡觉洗澡等日常安排，应判断为 skipped。
- 只表达“记一下”“别跳过”“以这条为准”但缺少可记内容时，应判断为 skipped；如果上下文能补全内容，则判断为 candidate。
- 不保存 API Key、密码、Token、住址、身份证、银行卡等高敏感隐私；涉及这些具体值时必须 skipped。
- 不把模型猜测当事实，不把群友隐私随便变成记忆。
- memory 必须写成第三人称事实，不要保留“我是...”“我喜欢...”这类第一人称原话。
- 如果消息中的“我 / 我的 / 本人”指发送者，应改写为“该用户 / 用户”；如果“你”指卡咔，应改写为“卡咔”。
- 示例：“我是物联网工程专业”应写为“该用户是物联网工程专业。”；“我一晚上做了 5 个项目”应写为“该用户一晚上做了 5 个项目。”

JSON 数组中每一项：
{
  "id": 123,
  "label": "candidate 或 skipped",
  "type": "user_fact / relationship_fact / important_event / stable_preference / none",
  "confidence": 0.0 到 1.0,
  "reason": "极短理由",
  "memory": "候选记忆；如果 label=skipped，填空字符串"
}
"""


@dataclass(frozen=True)
class AnalysisFilters:
    limit: int
    input_ids: tuple[int, ...] = ()
    group_id: str | None = None
    user_id: str | None = None
    target_date: date | None = None
    scene_type: str | None = None
    use_llm: bool = False
    use_llm_batch: bool = False
    mark_skipped: bool = False
    write_candidates: bool = False


@dataclass(frozen=True)
class ClassifiedInput:
    input_record: InputRecord
    user: UserRecord
    scene: SceneRecord
    result: AnalysisResult

    @property
    def scene_key(self) -> tuple[str, str, str]:
        return (self.scene.platform, self.scene.scene_type, self.scene.scene_id)


@dataclass(frozen=True)
class AnalysisResult:
    label: str
    reason: str

    @property
    def can_mark_skipped(self) -> bool:
        return self.label == "skipped"


@dataclass(frozen=True)
class LLMAnalysisResult:
    label: str
    memory_type: str
    confidence: float
    reason: str
    suggested_memory: str = ""
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass(frozen=True)
class BatchParseResult:
    results: dict[int, LLMAnalysisResult]
    parse_failed: bool = False
    error: str | None = None


@dataclass
class BatchLLMStats:
    initial_batch_count: int = 0
    target_count: int = 0
    request_count: int = 0
    parse_failure_count: int = 0
    split_retry_count: int = 0
    api_error_count: int = 0
    missing_result_count: int = 0

    @property
    def retry_request_count(self) -> int:
        return max(0, self.request_count - self.initial_batch_count)


@dataclass
class CandidateWriteStats:
    rule_skipped_marked: int = 0
    llm_skipped_marked: int = 0
    rule_candidates_inserted: int = 0
    llm_candidates_inserted: int = 0
    existing_candidates: int = 0
    analyzed_marked: int = 0
    llm_errors_left_unprocessed: int = 0
    missing_llm_results: int = 0

    @property
    def total_skipped_marked(self) -> int:
        return self.rule_skipped_marked + self.llm_skipped_marked

    @property
    def total_candidates_inserted(self) -> int:
        return self.rule_candidates_inserted + self.llm_candidates_inserted


@dataclass(frozen=True)
class LLMAnalysisBatch:
    targets: list[ClassifiedInput]
    context_rows: list[ClassifiedInput]

    @property
    def target_ids(self) -> set[int]:
        return {item.input_record.id for item in self.targets}


def main() -> None:
    configure_console_output()
    asyncio.run(run())


def configure_console_output() -> None:
    """避免 Windows 控制台遇到表情等特殊字符时中断脚本。"""

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


async def run() -> None:
    args = parse_args()
    filters = build_filters(args)

    init_database()
    llm_router = build_llm_router(filters)
    session_factory = create_session_factory()
    with session_factory() as session:
        rows = load_unanalyzed_inputs(session, filters)
        if not rows:
            print("暂无符合条件的未分析输入。")
            return

        classified_rows = classify_rows(rows)
        batch_results: dict[int, LLMAnalysisResult] = {}
        if filters.use_llm_batch:
            batches = build_llm_batches(classified_rows)
            batch_stats = BatchLLMStats()
            print(format_batch_plan(classified_rows, batches, llm_router is not None))
            batch_results = await analyze_llm_batches(
                batches,
                llm_router,
                batch_stats,
            )
            print(format_batch_execution_summary(batch_stats, batch_results))

        write_stats: CandidateWriteStats | None = None
        if filters.write_candidates:
            if llm_router is None:
                print("LLM 不可用，已跳过 --write-candidates，本次未修改数据库。")
            else:
                settings = get_settings()
                write_stats = write_candidates_and_mark_inputs(
                    session,
                    classified_rows,
                    batch_results,
                    analysis_model=settings.llm.memory_model,
                    analysis_prompt_version=LLM_BATCH_ANALYSIS_PROMPT_VERSION,
                )
                session.commit()

        skipped_ids: list[int] = []
        print(format_filter_summary(filters))
        for index, item in enumerate(classified_rows, start=1):
            input_record = item.input_record
            result = item.result
            if filters.mark_skipped and not filters.write_candidates and result.can_mark_skipped:
                input_record.analysis_status = ANALYSIS_STATUS_SKIPPED
                skipped_ids.append(input_record.id)
            if filters.use_llm_batch and result.label != "not_sure":
                continue
            llm_result = None
            if filters.use_llm_batch and result.label == "not_sure":
                llm_result = batch_results.get(input_record.id)
            elif filters.use_llm and result.label == "not_sure":
                llm_result = await analyze_not_sure_with_llm(
                    item.input_record,
                    item.user,
                    item.scene,
                    llm_router,
                )
            print(
                format_analysis(
                    index,
                    item.input_record,
                    item.user,
                    item.scene,
                    result,
                    llm_result,
                )
            )

        if filters.write_candidates and write_stats is not None:
            print(format_candidate_write_summary(write_stats))
        elif filters.mark_skipped:
            session.commit()
            print(f"已标记 skipped：{len(skipped_ids)} 条。")
        else:
            print(
                "只读预览：未修改数据库。需要写入候选区并标记处理状态时，加 --write-candidates。"
            )


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(None)
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    args = ["--limit", str(PYCHARM_LIMIT)]
    ids_text = PYCHARM_INPUT_IDS.strip()
    if ids_text:
        args.extend(["--ids", ids_text])
    group_id = PYCHARM_GROUP_ID.strip()
    if group_id:
        args.extend(["--group", group_id])
    user_id = PYCHARM_USER_ID.strip()
    if user_id:
        args.extend(["--user", user_id])
    target_date = PYCHARM_DATE.strip()
    if target_date:
        args.extend(["--date", target_date])

    if PYCHARM_PRIVATE and PYCHARM_GROUP_CHAT:
        raise SystemExit("PYCHARM_PRIVATE 和 PYCHARM_GROUP_CHAT 不能同时为 True。")
    if PYCHARM_PRIVATE:
        args.append("--private")
    if PYCHARM_GROUP_CHAT:
        args.append("--group-chat")

    if PYCHARM_LLM and PYCHARM_LLM_BATCH:
        raise SystemExit("PYCHARM_LLM 和 PYCHARM_LLM_BATCH 不能同时为 True。")
    if PYCHARM_LLM:
        args.append("--llm")
    if PYCHARM_LLM_BATCH:
        args.append("--llm-batch")

    if PYCHARM_WRITE_CANDIDATES:
        args.append("--write-candidates")
    if PYCHARM_MARK_SKIPPED:
        args.append("--mark-skipped")
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="分析卡咔未处理的输入记录。")
    parser.add_argument("--id", dest="input_ids", action="append", type=int, help="指定单个输入 ID，可重复传入。")
    parser.add_argument("--ids", help="逗号分隔的输入 ID 列表，例如 12,13,14。")
    parser.add_argument("--limit", type=int, default=20, help="显示最近多少条，默认 20。")
    parser.add_argument("--group", dest="group_id", help="只看指定 QQ 群号。")
    parser.add_argument("--user", dest="user_id", help="只看指定 QQ 用户。")
    parser.add_argument("--date", dest="target_date", help="只看指定日期，格式为 YYYY-MM-DD，按北京时间理解。")
    scene_group = parser.add_mutually_exclusive_group()
    scene_group.add_argument("--private", action="store_true", help="只看私聊。")
    scene_group.add_argument("--group-chat", action="store_true", help="只看群聊。")
    parser.add_argument("--llm", action="store_true", help="只读调用大模型分析 not_sure 记录。")
    parser.add_argument("--llm-batch", action="store_true", help="只读批量调用大模型分析 not_sure 记录。")
    parser.add_argument("--mark-skipped", action="store_true", help="把明显无价值记录标记为 skipped。")
    parser.add_argument(
        "--write-candidates",
        action="store_true",
        help="写入 memory_candidates，并把已处理的 input 标记为 analyzed/skipped。",
    )
    args = parser.parse_args(argv)
    if args.llm and args.llm_batch:
        parser.error("--llm 和 --llm-batch 不能同时使用。")
    if args.write_candidates and not args.llm_batch:
        parser.error("--write-candidates 必须和 --llm-batch 一起使用。")
    if args.write_candidates and args.mark_skipped:
        parser.error("--write-candidates 已包含 skipped 标记，不要同时使用 --mark-skipped。")
    return args


def build_filters(args: argparse.Namespace) -> AnalysisFilters:
    if args.limit <= 0:
        raise SystemExit("--limit 必须大于 0。")

    scene_type = None
    if args.private:
        scene_type = "private"
    elif args.group_chat:
        scene_type = "group"

    target_date = None
    if args.target_date:
        try:
            target_date = date.fromisoformat(args.target_date)
        except ValueError as exc:
            raise SystemExit("--date 格式必须是 YYYY-MM-DD，例如 2026-05-01。") from exc

    return AnalysisFilters(
        limit=args.limit,
        input_ids=parse_input_ids(args.input_ids, args.ids),
        group_id=normalize_optional_id(args.group_id),
        user_id=normalize_optional_id(args.user_id),
        target_date=target_date,
        scene_type=scene_type,
        use_llm=args.llm,
        use_llm_batch=args.llm_batch,
        mark_skipped=args.mark_skipped,
        write_candidates=args.write_candidates,
    )


def normalize_optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_input_ids(input_ids: list[int] | None, ids_text: str | None) -> tuple[int, ...]:
    values: list[int] = []
    for item in input_ids or []:
        if item > 0:
            values.append(item)
    if ids_text:
        for piece in ids_text.split(","):
            piece = piece.strip()
            if not piece:
                continue
            try:
                number = int(piece)
            except ValueError:
                raise SystemExit(f"无效的 input_id: {piece}") from None
            if number > 0:
                values.append(number)

    seen: set[int] = set()
    unique: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)


def load_unanalyzed_inputs(
        session: Session,
        filters: AnalysisFilters,
) -> list[tuple[InputRecord, UserRecord, SceneRecord]]:
    statement = (
        select(InputRecord, UserRecord, SceneRecord)
        .join(UserRecord, InputRecord.user_id == UserRecord.id)
        .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
        .where(InputRecord.analysis_status == ANALYSIS_STATUS_NOT_ANALYZED)
    )

    if filters.input_ids:
        statement = statement.where(InputRecord.id.in_(filters.input_ids))

    if filters.user_id:
        statement = statement.where(UserRecord.platform_user_id == filters.user_id)

    if filters.group_id:
        statement = statement.where(
            SceneRecord.scene_type == "group",
            SceneRecord.scene_id == filters.group_id,
        )

    if filters.scene_type:
        statement = statement.where(SceneRecord.scene_type == filters.scene_type)

    if filters.target_date:
        start_utc, end_utc = local_date_to_utc_range(filters.target_date)
        statement = statement.where(
            InputRecord.created_at >= start_utc,
            InputRecord.created_at < end_utc,
        )

    statement = statement.order_by(InputRecord.created_at.desc()).limit(filters.limit)
    return list(session.execute(statement).all())


def classify_rows(
    rows: list[tuple[InputRecord, UserRecord, SceneRecord]],
) -> list[ClassifiedInput]:
    """给数据库行附加当前规则分析结果。"""

    return [
        ClassifiedInput(
            input_record=input_record,
            user=user,
            scene=scene,
            result=classify_input_text(input_record.content_text),
        )
        for input_record, user, scene in rows
    ]


def classify_input_text(text: str | None) -> AnalysisResult:
    value = (text or "").strip()
    normalized_value = normalize_text_for_matching(value)
    if not value:
        return AnalysisResult("skipped", "空文本")

    if value in SKIP_EXACT_TEXTS:
        return AnalysisResult("skipped", "占位消息，暂不进入分析")

    if PUNCTUATION_RE.match(value):
        return AnalysisResult("skipped", "只有符号或空白")

    if normalized_value in COMMON_LOW_VALUE_TEXTS:
        return AnalysisResult("skipped", "常见寒暄或低信息量回应")

    for reason, pattern in SENSITIVE_PATTERNS:
        if pattern.search(normalized_value):
            return AnalysisResult("skipped", reason)

    if is_test_message(value):
        return AnalysisResult("skipped", "测试消息")

    if len(value) <= 2 and not contains_cjk_digit_or_letter(value):
        return AnalysisResult("skipped", "过短且缺少有效内容")

    for reason, pattern in CANDIDATE_PATTERNS:
        if pattern.search(value):
            return AnalysisResult("candidate", reason)

    for reason, pattern in LOW_VALUE_PATTERNS:
        if pattern.search(normalized_value):
            return AnalysisResult("skipped", reason)

    if len(value) <= 4:
        return AnalysisResult("not_sure", "短文本，暂不自动跳过")

    return AnalysisResult("not_sure", "普通聊天，后续可接入更细分析")


def normalize_text_for_matching(value: str) -> str:
    """把常见尾部语气符号去掉，降低规则误差。"""

    text = value.strip()
    text = re.sub(r"[\s。.!！?？~～…]+$", "", text)
    return text.lower()


def is_test_message(value: str) -> bool:
    """识别开发期间产生的低价值测试消息。"""

    lower_value = value.lower()
    if "测试" not in lower_value and "test" not in lower_value:
        return False
    if any(
        keyword in value
        for keyword in (
            "不要污染",
            "临时数据库",
            "测试样例",
            "测试数据",
            "验证",
        )
    ):
        return False
    return len(value) <= 12


def contains_cjk_digit_or_letter(value: str) -> bool:
    for char in value:
        if "\u4e00" <= char <= "\u9fff":
            return True
        if char.isascii() and char.isalnum():
            return True
    return False


def write_candidates_and_mark_inputs(
    session: Session,
    classified_rows: list[ClassifiedInput],
    batch_results: dict[int, LLMAnalysisResult],
    *,
    analysis_model: str,
    analysis_prompt_version: str,
) -> CandidateWriteStats:
    """把候选写入 memory_candidates，并标记已处理 input。"""

    stats = CandidateWriteStats()
    existing_candidate_keys = load_existing_candidate_keys(session, classified_rows)
    for item in classified_rows:
        input_record = item.input_record
        result = item.result
        if result.label == "skipped":
            input_record.analysis_status = ANALYSIS_STATUS_SKIPPED
            stats.rule_skipped_marked += 1
            continue
        if result.label == "candidate":
            inserted = add_memory_candidate_if_missing(
                session,
                item,
                memory_text=input_record.content_text or "",
                memory_type=infer_rule_memory_type(
                    result.reason,
                    input_record.content_text or "",
                ),
                confidence=0.75,
                reason=f"规则候选：{result.reason}",
                analysis_model=RULE_ANALYSIS_MODEL,
                analysis_prompt_version=RULE_ANALYSIS_PROMPT_VERSION,
                existing_candidate_keys=existing_candidate_keys,
            )
            if inserted:
                stats.rule_candidates_inserted += 1
            else:
                stats.existing_candidates += 1
            input_record.analysis_status = ANALYSIS_STATUS_ANALYZED
            stats.analyzed_marked += 1
            continue

        llm_result = batch_results.get(input_record.id)
        if llm_result is None:
            stats.missing_llm_results += 1
            continue
        if llm_result.is_error:
            stats.llm_errors_left_unprocessed += 1
            continue
        if llm_result.label == "skipped":
            input_record.analysis_status = ANALYSIS_STATUS_SKIPPED
            stats.llm_skipped_marked += 1
            continue
        if llm_result.label == "candidate":
            inserted = add_memory_candidate_if_missing(
                session,
                item,
                memory_text=llm_result.suggested_memory,
                memory_type=llm_result.memory_type,
                confidence=llm_result.confidence,
                reason=llm_result.reason,
                analysis_model=analysis_model,
                analysis_prompt_version=analysis_prompt_version,
                existing_candidate_keys=existing_candidate_keys,
            )
            if inserted:
                stats.llm_candidates_inserted += 1
            else:
                stats.existing_candidates += 1
            input_record.analysis_status = ANALYSIS_STATUS_ANALYZED
            stats.analyzed_marked += 1

    return stats


def load_existing_candidate_keys(
    session: Session,
    classified_rows: list[ClassifiedInput],
) -> set[tuple[int, str, str]]:
    source_ids = [item.input_record.id for item in classified_rows]
    if not source_ids:
        return set()
    rows = session.execute(
        select(
            MemoryCandidateRecord.source_input_id,
            MemoryCandidateRecord.memory_type,
            MemoryCandidateRecord.candidate_memory,
        ).where(
            MemoryCandidateRecord.source_input_id.in_(source_ids)
        )
    )
    return {
        (int(source_input_id), str(memory_type), normalize_memory_key(candidate_memory))
        for source_input_id, memory_type, candidate_memory in rows
    }


def add_memory_candidate_if_missing(
    session: Session,
    item: ClassifiedInput,
    *,
    memory_text: str,
    memory_type: str,
    confidence: float,
    reason: str,
    analysis_model: str,
    analysis_prompt_version: str,
    existing_candidate_keys: set[tuple[int, str, str]],
) -> bool:
    input_record = item.input_record
    candidate_memory = normalize_candidate_memory_expression(
        memory_text or input_record.content_text or ""
    )
    if not candidate_memory:
        return False
    key = (input_record.id, memory_type, normalize_memory_key(candidate_memory))
    if key in existing_candidate_keys:
        return False

    session.add(
        MemoryCandidateRecord(
            source_input_id=input_record.id,
            source_user_id=item.user.id,
            source_scene_id=item.scene.id,
            source_text=input_record.content_text or "",
            candidate_memory=candidate_memory,
            memory_type=memory_type,
            confidence=normalize_confidence(confidence),
            reason=reason[:500],
            analysis_model=analysis_model,
            analysis_prompt_version=analysis_prompt_version,
            status=MEMORY_CANDIDATE_STATUS_PENDING,
        )
    )
    existing_candidate_keys.add(key)
    return True


def normalize_memory_key(value: str | None) -> str:
    """归一化候选正文，用于同一输入内的基础去重。"""

    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[。.!！?？~～…]+$", "", text)
    return text


def normalize_candidate_memory_expression(value: str) -> str:
    """把明显的第一人称候选改成当前用户画像表达。

    这里只做很保守的前缀处理，复杂指代仍交给候选复核的大模型。
    """

    text = str(value or "").strip()
    if not text:
        return ""

    replacements = (
        ("我自己", "该用户自己"),
        ("我的", "该用户的"),
        ("本人", "该用户"),
        ("我", "该用户"),
    )
    for source, target in replacements:
        if text.startswith(source):
            return f"{target}{text[len(source):]}"
    return text


def infer_rule_memory_type(reason: str, text: str = "") -> str:
    normalized_reason = normalize_text_for_matching(reason)
    normalized_text = normalize_text_for_matching(text)
    if is_preference_hint(normalized_reason) or is_preference_hint(normalized_text):
        return "stable_preference"
    if is_relationship_hint(normalized_reason) or is_relationship_hint(normalized_text):
        return "relationship_fact"
    if "计划" in normalized_reason or "节点" in normalized_reason:
        return "important_event"
    if "计划" in normalized_text or "节点" in normalized_text:
        return "important_event"
    return "user_fact"


def is_preference_hint(value: str) -> bool:
    return bool(
        re.search(
            r"(我喜欢|我不喜欢|我更喜欢|我最喜欢|我希望|我更希望|我不希望|我习惯|我讨厌|"
            r"偏好|以后都|之后都|别叫我|不要叫我|可以叫我|"
            r"回答时|回复时|说话方式|语气|风格|不要.*卖萌|解释.*原因|先.*说明|别.*装)",
            value,
        )
    )


def is_relationship_hint(value: str) -> bool:
    return bool(
        re.search(
            r"(他是我|她是我|ta是我|TA是我|他是我的|她是我的|ta是我的|TA是我的|"
            r"我是他|我是她|这是我|这个是我|那是我|这个人是我|那个人是我|"
            r"朋友|同学|室友|舍友|对象|男朋友|女朋友|兄弟|亲友|熟人|维护者)",
            value,
        )
    )


def build_llm_router(filters: AnalysisFilters) -> LLMRouter | None:
    """按需创建 LLMRouter。

    默认规则分析不需要模型。只有显式加 --llm / --llm-batch 时，才读取模型配置。
    """

    if not filters.use_llm and not filters.use_llm_batch:
        return None

    settings = get_settings()
    if not settings.llm.can_call_remote:
        print("LLM 分析已请求，但 LLM 未启用或缺少 LLM_API_KEY；本次只显示规则结果。")
        return None

    return LLMRouter(settings.llm)


async def analyze_not_sure_with_llm(
    input_record: InputRecord,
    user: UserRecord,
    scene: SceneRecord,
    router: LLMRouter | None,
) -> LLMAnalysisResult | None:
    """让大模型只读判断一条规则不确定的输入。"""

    if router is None:
        return None

    prompt = build_llm_analysis_prompt(input_record, user, scene)
    try:
        raw_reply = await router.summarize_memory(
            [
                ChatMessage(role="system", content=LLM_ANALYSIS_SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ]
        )
    except LLMClientError as exc:
        return LLMAnalysisResult(
            label="error",
            memory_type="none",
            confidence=0.0,
            reason="LLM 调用失败",
            error=str(exc),
        )

    return parse_llm_analysis_reply(raw_reply)


def build_llm_analysis_prompt(
    input_record: InputRecord,
    user: UserRecord,
    scene: SceneRecord,
) -> str:
    """构造单条输入的 LLM 判断提示。"""

    display_name = user.display_name or user.platform_user_id
    local_time = format_local_time(input_record.created_at)
    message_text = input_record.content_text or ""
    return "\n".join(
        [
            "请判断下面这条输入是否值得进入长期记忆候选区。",
            f"时间：{local_time}",
            f"平台：{scene.platform}",
            f"场景：{format_scene_type(scene.scene_type)} / {scene.scene_id}",
            f"用户：{display_name}（{user.platform_user_id}）",
            f"消息：{message_text}",
        ]
    )


def parse_llm_analysis_reply(raw_reply: str) -> LLMAnalysisResult:
    """解析大模型返回的 JSON，并做保守规范化。"""

    try:
        data = json.loads(extract_json_object(raw_reply))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return LLMAnalysisResult(
            label="error",
            memory_type="none",
            confidence=0.0,
            reason="LLM 返回不是有效 JSON",
            error=f"{exc}: {raw_reply[:200]}",
        )

    label = normalize_llm_label(data.get("label"))
    memory_type = normalize_memory_type(data.get("memory_type"), label=label)
    confidence = normalize_confidence(data.get("confidence"))
    reason = str(data.get("reason") or "").strip()[:200] or "未给出理由"
    suggested_memory = str(data.get("suggested_memory") or "").strip()
    if label != "candidate":
        suggested_memory = ""

    return LLMAnalysisResult(
        label=label,
        memory_type=memory_type,
        confidence=confidence,
        reason=reason,
        suggested_memory=suggested_memory,
    )


def extract_json_object(raw_reply: str) -> str:
    """从模型回复中提取 JSON 对象。"""

    text = raw_reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("未找到 JSON 对象")
    return text[start : end + 1]


def normalize_llm_label(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "candidate":
        return "candidate"
    return "skipped"


def normalize_memory_type(value: object, *, label: str) -> str:
    if label != "candidate":
        return "none"

    text = str(value or "").strip().lower()
    allowed = {
        "user_fact",
        "relationship_fact",
        "important_event",
        "stable_preference",
    }
    if text in allowed:
        return text
    return "user_fact"


def normalize_confidence(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


async def analyze_batches_with_llm(
    classified_rows: list[ClassifiedInput],
    router: LLMRouter | None,
) -> dict[int, LLMAnalysisResult]:
    """批量让大模型只读判断 not_sure 输入。"""

    return await analyze_llm_batches(build_llm_batches(classified_rows), router)


async def analyze_llm_batches(
    batches: list[LLMAnalysisBatch],
    router: LLMRouter | None,
    stats: BatchLLMStats | None = None,
) -> dict[int, LLMAnalysisResult]:
    """执行已经构造好的 LLM 批量分析包。"""

    stats = stats or BatchLLMStats()
    stats.initial_batch_count = len(batches)
    stats.target_count = sum(len(batch.targets) for batch in batches)
    if router is None:
        return {}

    results: dict[int, LLMAnalysisResult] = {}
    for batch in batches:
        results.update(await analyze_batch_with_llm(batch, router, stats))
    return results


def build_llm_batches(classified_rows: list[ClassifiedInput]) -> list[LLMAnalysisBatch]:
    """按场景和时间把 not_sure 输入打包。"""

    ordered_rows = sorted(
        classified_rows,
        key=lambda item: (
            item.scene_key,
            item.input_record.created_at,
            item.input_record.id,
        ),
    )
    rows_by_scene: dict[tuple[str, str, str], list[ClassifiedInput]] = {}
    for item in ordered_rows:
        rows_by_scene.setdefault(item.scene_key, []).append(item)

    batches: list[LLMAnalysisBatch] = []
    for scene_rows in rows_by_scene.values():
        targets = [item for item in scene_rows if item.result.label == "not_sure"]
        for target_group in split_not_sure_targets(targets):
            context_rows = select_batch_context(scene_rows, target_group)
            batches.append(LLMAnalysisBatch(targets=target_group, context_rows=context_rows))

    return batches


def split_not_sure_targets(targets: list[ClassifiedInput]) -> list[list[ClassifiedInput]]:
    """把同一场景里的 not_sure 记录按数量和时间跨度拆包。"""

    groups: list[list[ClassifiedInput]] = []
    current: list[ClassifiedInput] = []
    current_start: datetime | None = None

    for target in targets:
        created_at = ensure_aware_utc(target.input_record.created_at)
        should_start_new = False
        if current and len(current) >= BATCH_NOT_SURE_SIZE:
            should_start_new = True
        if current_start is not None and created_at - current_start > BATCH_MAX_SPAN:
            should_start_new = True

        if should_start_new:
            groups.append(current)
            current = []
            current_start = None

        if current_start is None:
            current_start = created_at
        current.append(target)

    if current:
        groups.append(current)
    return groups


def select_batch_context(
    scene_rows: list[ClassifiedInput],
    targets: list[ClassifiedInput],
) -> list[ClassifiedInput]:
    """选择一包 not_sure 的前后上下文。"""

    target_ids = {item.input_record.id for item in targets}
    first_target = targets[0]
    last_target = targets[-1]
    first_time = ensure_aware_utc(first_target.input_record.created_at)
    last_time = ensure_aware_utc(last_target.input_record.created_at)

    first_index = scene_rows.index(first_target)
    last_index = scene_rows.index(last_target)

    before_candidates = [
        item
        for item in scene_rows[:first_index]
        if first_time - ensure_aware_utc(item.input_record.created_at)
        <= BATCH_CONTEXT_TIME_WINDOW
    ][-BATCH_CONTEXT_BEFORE_COUNT:]
    after_candidates = [
        item
        for item in scene_rows[last_index + 1 :]
        if ensure_aware_utc(item.input_record.created_at) - last_time
        <= BATCH_CONTEXT_TIME_WINDOW
    ][:BATCH_CONTEXT_AFTER_COUNT]

    context_rows = before_candidates + targets + after_candidates
    deduplicated: list[ClassifiedInput] = []
    seen_ids: set[int] = set()
    for item in context_rows:
        input_id = item.input_record.id
        if input_id in seen_ids:
            continue
        seen_ids.add(input_id)
        deduplicated.append(item)

    return sorted(
        deduplicated,
        key=lambda item: (
            ensure_aware_utc(item.input_record.created_at),
            item.input_record.id,
            item.input_record.id not in target_ids,
        ),
    )


async def analyze_batch_with_llm(
    batch: LLMAnalysisBatch,
    router: LLMRouter,
    stats: BatchLLMStats | None = None,
) -> dict[int, LLMAnalysisResult]:
    return await analyze_batch_with_llm_retry(batch, router, stats or BatchLLMStats())


async def analyze_batch_with_llm_retry(
    batch: LLMAnalysisBatch,
    router: LLMRouter,
    stats: BatchLLMStats | None = None,
) -> dict[int, LLMAnalysisResult]:
    stats = stats or BatchLLMStats()
    parse_result = await request_and_parse_llm_batch(batch, router, stats)
    if not parse_result.parse_failed:
        return fill_missing_batch_results(batch, parse_result.results, stats)

    stats.parse_failure_count += 1
    if len(batch.targets) <= 1:
        return {
            item.input_record.id: LLMAnalysisResult(
                label="error",
                memory_type="none",
                confidence=0.0,
                reason="LLM 批量返回解析失败",
                error=parse_result.error or "parse_failed",
            )
            for item in batch.targets
        }

    stats.split_retry_count += 1
    merged: dict[int, LLMAnalysisResult] = {}
    for child in split_batch_for_retry(batch):
        merged.update(await analyze_batch_with_llm_retry(child, router, stats))
    return merged


async def request_and_parse_llm_batch(
    batch: LLMAnalysisBatch,
    router: LLMRouter,
    stats: BatchLLMStats | None = None,
) -> BatchParseResult:
    prompt = build_llm_batch_analysis_prompt(batch)
    if stats is not None:
        stats.request_count += 1
    try:
        raw_reply = await router.summarize_memory(
            [
                ChatMessage(role="system", content=LLM_BATCH_ANALYSIS_SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ]
        )
    except LLMClientError as exc:
        if stats is not None:
            stats.api_error_count += 1
        return BatchParseResult(
            results={
                item.input_record.id: LLMAnalysisResult(
                    label="error",
                    memory_type="none",
                    confidence=0.0,
                    reason="LLM 调用失败",
                    error=str(exc),
                )
                for item in batch.targets
            },
            parse_failed=False,
            error=str(exc),
        )

    return parse_llm_batch_analysis_reply(raw_reply, batch.target_ids)


def fill_missing_batch_results(
    batch: LLMAnalysisBatch,
    parsed_results: dict[int, LLMAnalysisResult],
    stats: BatchLLMStats | None = None,
) -> dict[int, LLMAnalysisResult]:
    for item in batch.targets:
        if item.input_record.id in parsed_results:
            continue
        if stats is not None:
            stats.missing_result_count += 1
        parsed_results[item.input_record.id] = LLMAnalysisResult(
                label="error",
                memory_type="none",
                confidence=0.0,
                reason="LLM 未返回此 input_id 的结果",
                error=f"missing input_id={item.input_record.id}",
        )
    return parsed_results


def split_batch_for_retry(batch: LLMAnalysisBatch) -> list[LLMAnalysisBatch]:
    midpoint = max(1, len(batch.targets) // 2)
    target_groups = [batch.targets[:midpoint], batch.targets[midpoint:]]
    return [
        LLMAnalysisBatch(
            targets=target_group,
            context_rows=select_retry_context(batch.context_rows, target_group),
        )
        for target_group in target_groups
        if target_group
    ]


def select_retry_context(
    parent_context_rows: list[ClassifiedInput],
    targets: list[ClassifiedInput],
) -> list[ClassifiedInput]:
    target_ids = {item.input_record.id for item in targets}
    first_target = targets[0]
    last_target = targets[-1]
    first_time = ensure_aware_utc(first_target.input_record.created_at)
    last_time = ensure_aware_utc(last_target.input_record.created_at)

    before = [
        item
        for item in parent_context_rows
        if item.input_record.id not in target_ids
        and ensure_aware_utc(item.input_record.created_at) < first_time
        and first_time - ensure_aware_utc(item.input_record.created_at)
        <= BATCH_CONTEXT_TIME_WINDOW
    ][-BATCH_CONTEXT_BEFORE_COUNT:]
    after = [
        item
        for item in parent_context_rows
        if item.input_record.id not in target_ids
        and ensure_aware_utc(item.input_record.created_at) > last_time
        and ensure_aware_utc(item.input_record.created_at) - last_time
        <= BATCH_CONTEXT_TIME_WINDOW
    ][:BATCH_CONTEXT_AFTER_COUNT]

    combined = before + targets + after
    return sorted(
        combined,
        key=lambda item: (ensure_aware_utc(item.input_record.created_at), item.input_record.id),
    )


def build_llm_batch_analysis_prompt(batch: LLMAnalysisBatch) -> str:
    """构造批量 LLM 判断提示。"""

    scene = batch.targets[0].scene
    target_ids = sorted(batch.target_ids)
    lines = [
        "请根据下面同一场景的聊天片段，判断 target=true 的输入是否值得进入长期记忆候选区。",
        f"场景：{scene.platform} / {format_scene_type(scene.scene_type)} / {scene.scene_id}",
        f"需要判断的 input_id：{target_ids}",
        "聊天片段：",
    ]
    for item in batch.context_rows:
        input_record = item.input_record
        user = item.user
        is_target = input_record.id in batch.target_ids
        display_name = user.display_name or user.platform_user_id
        lines.append(
            json.dumps(
                {
                    "input_id": input_record.id,
                    "target": is_target,
                    "time": format_local_time(input_record.created_at),
                    "user_id": user.platform_user_id,
                    "display_name": display_name,
                    "rule_label": item.result.label,
                    "text": input_record.content_text or "",
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def parse_llm_batch_analysis_reply(
    raw_reply: str,
    target_ids: set[int],
) -> BatchParseResult:
    """解析批量 LLM 返回的 JSON 数组。"""

    try:
        data = json.loads(extract_json_array(raw_reply))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return BatchParseResult(
            results={},
            parse_failed=True,
            error=f"LLM 批量返回不是有效 JSON 数组：{exc}: {raw_reply[:200]}",
        )

    if not isinstance(data, list):
        return BatchParseResult(
            results={},
            parse_failed=True,
            error=f"LLM 批量返回不是 JSON 数组：{raw_reply[:200]}",
        )

    results: dict[int, LLMAnalysisResult] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        input_id = normalize_input_id(item.get("id", item.get("input_id")))
        if input_id is None or input_id not in target_ids:
            continue
        label = normalize_llm_label(item.get("label"))
        memory_type = normalize_memory_type(item.get("type", item.get("memory_type")), label=label)
        confidence = normalize_confidence(item.get("confidence"))
        reason = str(item.get("reason") or "").strip()[:200] or "未给出理由"
        suggested_memory = str(item.get("memory", item.get("suggested_memory")) or "").strip()
        if label != "candidate":
            suggested_memory = ""
        results[input_id] = LLMAnalysisResult(
            label=label,
            memory_type=memory_type,
            confidence=confidence,
            reason=reason,
            suggested_memory=suggested_memory,
        )

    if target_ids and not results:
        return BatchParseResult(
            results={},
            parse_failed=True,
            error=f"LLM 批量返回没有可用的目标 input_id：{raw_reply[:200]}",
        )
    return BatchParseResult(results=results)


def extract_json_array(raw_reply: str) -> str:
    """从模型回复中提取 JSON 数组。"""

    text = raw_reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("未找到 JSON 数组")
    return text[start : end + 1]


def normalize_input_id(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_batch_plan(
    classified_rows: list[ClassifiedInput],
    batches: list[LLMAnalysisBatch],
    can_call_llm: bool,
) -> str:
    """格式化批量 LLM 分析计划，方便人工确认每包内容。"""

    counts = count_rule_labels(classified_rows)
    target_count = sum(len(batch.targets) for batch in batches)
    context_count = sum(
        len([item for item in batch.context_rows if item.input_record.id not in batch.target_ids])
        for batch in batches
    )
    lines = [
        "",
        "批量 LLM 分析计划",
        "=" * 60,
        f"LLM 状态：{'将调用大模型' if can_call_llm else '不会调用大模型，配置不可用或缺少 Key'}",
        f"规则统计：skipped={counts.get('skipped', 0)} / candidate={counts.get('candidate', 0)} / not_sure={counts.get('not_sure', 0)}",
        f"打包参数：每包最多 {BATCH_NOT_SURE_SIZE} 条 not_sure；包内跨度 <= {format_timedelta(BATCH_MAX_SPAN)}；上下文前 {BATCH_CONTEXT_BEFORE_COUNT} 后 {BATCH_CONTEXT_AFTER_COUNT}；上下文时间窗 {format_timedelta(BATCH_CONTEXT_TIME_WINDOW)}",
        f"模型初始包数：{len(batches)}",
        f"预计最低请求次数：{len(batches)}",
        f"需要模型判断：{target_count} 条 not_sure",
        f"上下文参考：{context_count} 条",
    ]
    if not batches:
        lines.append("没有需要批量分析的 not_sure。")
        lines.append("=" * 60)
        return "\n".join(lines)

    for index, batch in enumerate(batches, start=1):
        lines.extend(format_batch_detail(index, batch))
    lines.append("=" * 60)
    lines.append("下面逐条结果只显示 not_sure；skipped / candidate 已在包级计划里统计，不再展开。")
    return "\n".join(lines)


def format_batch_execution_summary(
    stats: BatchLLMStats,
    results: dict[int, LLMAnalysisResult],
) -> str:
    """格式化批量 LLM 实际执行统计。"""

    final_error_count = sum(1 for result in results.values() if result.is_error)
    candidate_count = sum(1 for result in results.values() if result.label == "candidate")
    skipped_count = sum(1 for result in results.values() if result.label == "skipped")
    lines = [
        "",
        "批量 LLM 执行结果",
        "=" * 60,
        f"初始包数：{stats.initial_batch_count}",
        f"需要判断：{stats.target_count} 条 not_sure",
        f"实际请求次数：{stats.request_count}",
        f"自动拆包重试：{stats.split_retry_count} 次",
        f"重试新增请求：{stats.retry_request_count} 次",
        f"解析失败触发：{stats.parse_failure_count} 次",
        f"API 调用失败：{stats.api_error_count} 次",
        f"模型漏返结果：{stats.missing_result_count} 条",
        f"最终结果：candidate={candidate_count} / skipped={skipped_count} / error={final_error_count}",
        "=" * 60,
    ]
    return "\n".join(lines)


def format_candidate_write_summary(stats: CandidateWriteStats) -> str:
    lines = [
        "",
        "候选区写入结果",
        "=" * 60,
        f"新增候选：{stats.total_candidates_inserted} 条",
        f"  规则候选：{stats.rule_candidates_inserted} 条",
        f"  LLM 候选：{stats.llm_candidates_inserted} 条",
        f"已存在候选：{stats.existing_candidates} 条",
        f"标记 skipped：{stats.total_skipped_marked} 条",
        f"  规则 skipped：{stats.rule_skipped_marked} 条",
        f"  LLM skipped：{stats.llm_skipped_marked} 条",
        f"标记 analyzed：{stats.analyzed_marked} 条",
        f"LLM error 保持未处理：{stats.llm_errors_left_unprocessed} 条",
        f"缺少 LLM 结果保持未处理：{stats.missing_llm_results} 条",
        "=" * 60,
    ]
    return "\n".join(lines)


def count_rule_labels(classified_rows: list[ClassifiedInput]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in classified_rows:
        counts[item.result.label] = counts.get(item.result.label, 0) + 1
    return counts


def format_batch_detail(index: int, batch: LLMAnalysisBatch) -> list[str]:
    scene = batch.targets[0].scene
    target_times = [ensure_aware_utc(item.input_record.created_at) for item in batch.targets]
    context_only = [
        item for item in batch.context_rows if item.input_record.id not in batch.target_ids
    ]
    lines = [
        "",
        f"包 #{index}",
        f"  场景：{scene.platform} / {format_scene_type(scene.scene_type)} / {scene.scene_id}",
        f"  目标时间：{format_local_time(min(target_times))} -> {format_local_time(max(target_times))}",
        f"  目标条数：{len(batch.targets)}；上下文条数：{len(context_only)}；发送总条数：{len(batch.context_rows)}",
        f"  目标 input_id：{', '.join(str(item.input_record.id) for item in batch.targets)}",
    ]
    if context_only:
        lines.append(
            f"  上下文 input_id：{', '.join(str(item.input_record.id) for item in context_only)}"
        )
    else:
        lines.append("  上下文 input_id：无")
    lines.append("  发送内容：")
    for item in batch.context_rows:
        marker = "TARGET" if item.input_record.id in batch.target_ids else "CTX"
        text = compact_text(item.input_record.content_text or "")
        lines.append(
            f"    [{marker}] #{item.input_record.id} {format_local_time(item.input_record.created_at)} "
            f"{item.user.display_name or item.user.platform_user_id}: {text}"
        )
    return lines


def compact_text(value: str, limit: int = 80) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def format_timedelta(value: timedelta) -> str:
    total_seconds = int(value.total_seconds())
    if total_seconds % 60 == 0:
        return f"{total_seconds // 60} 分钟"
    return f"{total_seconds} 秒"


def format_filter_summary(filters: AnalysisFilters) -> str:
    parts = [f"limit={filters.limit}", f"status={ANALYSIS_STATUS_NOT_ANALYZED}"]
    if filters.group_id:
        parts.append(f"group={filters.group_id}")
    if filters.user_id:
        parts.append(f"user={filters.user_id}")
    if filters.target_date:
        parts.append(f"date={filters.target_date.isoformat()}")
    if filters.scene_type:
        parts.append(f"scene={format_scene_type(filters.scene_type)}")
    if filters.use_llm:
        parts.append("llm=true")
    if filters.use_llm_batch:
        parts.append("llm_batch=true")
    if filters.mark_skipped:
        parts.append("mark_skipped=true")
    if filters.write_candidates:
        parts.append("write_candidates=true")
    return "筛选条件：" + " / ".join(parts) + "\n"


def format_analysis(
        index: int,
        input_record: InputRecord,
        user: UserRecord,
        scene: SceneRecord,
        result: AnalysisResult,
        llm_result: LLMAnalysisResult | None = None,
) -> str:
    local_time = format_local_time(input_record.created_at)
    scene_label = format_scene(scene)
    display_name = user.display_name or user.platform_user_id

    lines = [
        f"[{index}] {local_time}  {scene_label}",
        f"用户：{display_name}（{user.platform_user_id}）",
        f"用户消息：{input_record.content_text or '(空文本)'}",
        f"规则结果：{result.label} / {result.reason}",
    ]
    if llm_result is not None:
        lines.extend(format_llm_analysis_lines(llm_result))
    lines.append("")
    return "\n".join(lines)


def format_llm_analysis_lines(result: LLMAnalysisResult) -> list[str]:
    if result.is_error:
        return [f"LLM建议：error / {result.error}"]

    lines = [
        f"LLM建议：{result.label}",
        f"记忆类型：{result.memory_type}",
        f"置信度：{result.confidence:.2f}",
        f"理由：{result.reason}",
    ]
    if result.suggested_memory:
        lines.append(f"建议记忆：{result.suggested_memory}")
    return lines


def format_local_time(value: datetime) -> str:
    """把数据库时间按协调世界时理解，并转成北京时间显示。"""

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def local_date_to_utc_range(value: date) -> tuple[datetime, datetime]:
    """把北京时间日期转换成数据库查询使用的协调世界时起止时间。"""

    start_local = datetime.combine(value, time.min, tzinfo=LOCAL_TZ)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def format_scene(scene: SceneRecord) -> str:
    scene_type = format_scene_type(scene.scene_type)
    return f"{scene.platform} / {scene_type} / {scene.scene_id}"


def format_scene_type(scene_type: str) -> str:
    scene_type_map = {
        "private": "私聊",
        "group": "群聊",
        "room": "房间",
        "device": "设备",
        "system": "系统",
    }
    return scene_type_map.get(scene_type, scene_type)


if __name__ == "__main__":
    main()
