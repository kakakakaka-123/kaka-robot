"""用大模型批量复核记忆候选。

这是测试阶段辅助脚本，用于临时代替人工判断候选是否可以进入正式 memories。
默认会调用大模型给出复核结果，但不修改数据库；确认后加 --apply 才写库。

如果已经在数据库可视化软件里看过 `memory_candidates.id`，PyCharm 右键运行时
优先改下面的简单配置：

    PYCHARM_CANDIDATE_IDS = "12,13"
    PYCHARM_APPLY = False

命令行示例：

    python services/kaka-core/scripts/review_memory_candidates.py --limit 20
    python services/kaka-core/scripts/review_memory_candidates.py --ids 12,13 --apply
    python services/kaka-core/scripts/review_memory_candidates.py --limit 20 --apply
    python services/kaka-core/scripts/review_memory_candidates.py --user 1419825488 --limit 20
    python services/kaka-core/scripts/review_memory_candidates.py --group 1073224364 --limit 20
    python services/kaka-core/scripts/review_memory_candidates.py --type user_fact --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "kaka-core" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaka_core.config.settings import get_settings  # noqa: E402
from kaka_core.llm.client import ChatMessage, LLMClientError  # noqa: E402
from kaka_core.llm.router import LLMRouter  # noqa: E402
from kaka_core.storage.database import create_session_factory, init_database  # noqa: E402
from kaka_core.storage.models import MemoryCandidateRecord, MemoryRecord, SceneRecord, UserRecord  # noqa: E402

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

PROMPT_VERSION = "llm-review-memory-candidate-v1"
MEMORY_STATUS_ACTIVE = "active"
MEMORY_SOURCE_CANDIDATE = "candidate"
CANDIDATE_STATUS_PENDING = "pending"
CANDIDATE_STATUS_APPROVED = "approved"
CANDIDATE_STATUS_DUPLICATE = "merged_duplicate"
CANDIDATE_STATUS_REJECTED = "rejected"
# LLM 复核失败的候选会落到这个终态，不再保持 pending 被每个整点反复重投。
# 候选数据仍保留，可在 /admin 查看，必要时手动改回 pending 重新复核。
CANDIDATE_STATUS_ERROR = "review_error"

VALID_ACTIONS = {"approve", "reject", "duplicate", "error"}
VALID_MEMORY_TYPES = {
    "user_fact",
    "relationship_fact",
    "important_event",
    "stable_preference",
}

FIRST_PERSON_RELATION_PATTERN = re.compile(
    r"^\s*(?:他|她|这|这个|那|那个)是我(?:的)?"
    r"(?P<relation>[\u4e00-\u9fffA-Za-z0-9_·-]{1,24})"
    r"(?:[，,](?P<detail>[^。.!！?？]{1,60}))?"
    r"[。.!！?？]?\s*$"
)

RELATION_LABELS = (
    "前端搭档",
    "后端搭档",
    "项目搭档",
    "室友",
    "导师",
    "老师",
    "同学",
    "同事",
    "朋友",
    "队友",
    "搭档",
    "老板",
    "领导",
    "妹妹",
    "姐姐",
    "哥哥",
    "弟弟",
    "妈妈",
    "爸爸",
)

REVIEW_SYSTEM_PROMPT = """你是卡咔 的长期记忆候选复核器。
你的任务是判断 memory_candidates.pending 是否应该进入正式 memories。

只允许输出 JSON 数组，不要输出 Markdown，不要解释 JSON 之外的内容。
输出必须尽量短，reason 不超过 24 个中文字符。

判断原则：
- approve：来源明确、长期有用、不会污染记忆，适合后续回复前作为上下文。
- reject：寒暄、玩笑、临时情绪、一次性日程、无明确对象、过度猜测、机器人自我台词、低价值闲聊、敏感信息，或候选正文明显不适合长期保存。
- duplicate：与 existing_memories 中已有 active 正式记忆语义相同或基本重复。
- 不要因为候选已经被写成一句话就盲目 approve，必须结合 source_text 判断是否有依据。
- 群聊中必须写清楚是谁的事实；不能把某人的话记到别人身上。
- “他是我/她是我/这是我...”这类关系句，如果说话人明确，属于关系事实，可以 approve 并改写成“某用户的...是...”。
- 示例：测试用户A说“他是我室友小陈，负责前端。”应 approve 为“测试用户A的室友小陈负责前端。”。
- 示例：测试用户B说“他是我导师王老师。”应 approve 为“测试用户B的导师是王老师。”。
- approve 的 memory 必须写成稳定、简洁的第三人称事实，不能以“我 / 我的 / 本人”表达。
- 候选或来源文本中的“我 / 我的 / 本人”默认指候选里的 user，不指卡咔；“你”如果是在对卡咔说话，应改写为“卡咔”。
- 示例：用户说“我是物联网工程专业。”应 approve 为“该用户是物联网工程专业。”。
- 示例：用户说“我希望你先给结论。”应 approve 为“该用户希望卡咔先给结论。”。
- 可以把 approve 的 memory 改写得更稳定、简洁、第三人称化，但不能新增来源没有的事实。
- 不保存 API Key、密码、Token、住址、身份证、银行卡等高敏感隐私。

JSON 数组中每一项：
{
  "id": 123,
  "action": "approve / reject / duplicate",
  "type": "user_fact / relationship_fact / important_event / stable_preference",
  "confidence": 0.0 到 1.0,
  "reason": "极短理由",
  "memory": "approve 时的正式记忆正文；reject/duplicate 时为空字符串"
}
"""

# PyCharm 简单模式：只改这里，再右键运行脚本。
# 多个候选 ID 用英文逗号隔开，例如 "12,13,14"。
# 不填 ID 时按 limit 复核 pending 候选。
PYCHARM_CANDIDATE_IDS = ""
PYCHARM_LIMIT = 20
PYCHARM_BATCH_SIZE = 5
PYCHARM_MEMORY_TYPE = ""
PYCHARM_GROUP_ID = ""
PYCHARM_USER_ID = ""
PYCHARM_MIN_CONFIDENCE = 0.0
PYCHARM_APPLY = False

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


@dataclass(frozen=True)
class ReviewFilters:
    limit: int
    batch_size: int
    candidate_ids: tuple[int, ...] = ()
    status: str = CANDIDATE_STATUS_PENDING
    memory_type: str | None = None
    group_id: str | None = None
    user_id: str | None = None
    min_confidence: float = 0.0
    apply: bool = False


@dataclass(frozen=True)
class CandidateReviewRow:
    candidate: MemoryCandidateRecord
    user: UserRecord
    scene: SceneRecord
    existing_memories: tuple[MemoryRecord, ...]


@dataclass(frozen=True)
class ReviewDecision:
    candidate: MemoryCandidateRecord
    action: str
    memory_text: str
    memory_type: str
    confidence: float
    reason: str
    duplicate_memory_id: int | None = None


@dataclass
class ReviewStats:
    approved: int = 0
    rejected: int = 0
    duplicates: int = 0
    errors: int = 0


def main() -> None:
    configure_console_output()
    asyncio.run(run())


def configure_console_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


async def run() -> None:
    args = parse_args()
    filters = build_filters(args)
    settings = get_settings()
    if not settings.llm.can_call_remote:
        raise SystemExit("LLM 未启用或缺少 LLM_API_KEY，无法复核候选。")

    init_database()
    session_factory = create_session_factory()
    router = LLMRouter(settings.llm)
    with session_factory() as session:
        rows = load_review_rows(session, filters)
        existing_keys = load_existing_memory_keys(session, {row.user.id for row in rows})
        decisions = await review_rows(rows, router, filters.batch_size, existing_keys)
        stats = apply_decisions(session, decisions) if filters.apply else ReviewStats()
        if filters.apply:
            session.commit()

    print(format_summary(filters, rows, decisions, stats))
    for index, decision in enumerate(decisions, start=1):
        print(format_decision(index, decision))


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(None)
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    args = ["--limit", str(PYCHARM_LIMIT), "--batch-size", str(PYCHARM_BATCH_SIZE)]
    ids_text = PYCHARM_CANDIDATE_IDS.strip()
    if ids_text:
        args.extend(["--ids", ids_text])
    memory_type = PYCHARM_MEMORY_TYPE.strip()
    if memory_type:
        args.extend(["--type", memory_type])
    group_id = PYCHARM_GROUP_ID.strip()
    if group_id:
        args.extend(["--group", group_id])
    user_id = PYCHARM_USER_ID.strip()
    if user_id:
        args.extend(["--user", user_id])
    if PYCHARM_MIN_CONFIDENCE > 0:
        args.extend(["--min-confidence", str(PYCHARM_MIN_CONFIDENCE)])
    if PYCHARM_APPLY:
        args.append("--apply")
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="用大模型批量复核长期记忆候选。")
    parser.add_argument("--id", dest="candidate_ids", action="append", type=int, help="指定单个候选 ID，可重复传入。")
    parser.add_argument("--ids", help="逗号分隔的候选 ID 列表，例如 12,13,14。")
    parser.add_argument("--limit", type=int, default=20, help="复核最近多少条候选，默认 20。")
    parser.add_argument("--batch-size", type=int, default=5, help="每次发给大模型的候选数，默认 5。")
    parser.add_argument("--status", default=CANDIDATE_STATUS_PENDING, help="候选状态，默认 pending。")
    parser.add_argument("--type", dest="memory_type", help="按记忆类型筛选。")
    parser.add_argument("--group", dest="group_id", help="只复核指定 QQ 群来源的候选。")
    parser.add_argument("--user", dest="user_id", help="只复核指定 QQ 用户来源的候选。")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="最低候选置信度，默认 0。")
    parser.add_argument("--apply", action="store_true", help="真正写入 memories 并更新候选状态。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> ReviewFilters:
    if args.limit <= 0:
        raise SystemExit("--limit 必须大于 0。")
    if args.batch_size <= 0 or args.batch_size > 20:
        raise SystemExit("--batch-size 必须在 1 到 20 之间。")
    if args.min_confidence < 0 or args.min_confidence > 1:
        raise SystemExit("--min-confidence 必须在 0 到 1 之间。")
    return ReviewFilters(
        limit=args.limit,
        batch_size=args.batch_size,
        candidate_ids=parse_candidate_ids(args.candidate_ids, args.ids),
        status=normalize_required_value(args.status),
        memory_type=normalize_optional_value(args.memory_type),
        group_id=normalize_optional_value(args.group_id),
        user_id=normalize_optional_value(args.user_id),
        min_confidence=args.min_confidence,
        apply=bool(args.apply),
    )


def parse_candidate_ids(candidate_ids: list[int] | None, ids_text: str | None) -> tuple[int, ...]:
    values: list[int] = []
    for item in candidate_ids or []:
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
                raise SystemExit(f"无效的 candidate_id: {piece}") from None
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


def normalize_required_value(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        raise SystemExit("状态不能为空。")
    return text


def normalize_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_review_rows(session: Session, filters: ReviewFilters) -> list[CandidateReviewRow]:
    statement = (
        select(MemoryCandidateRecord, UserRecord, SceneRecord)
        .join(UserRecord, MemoryCandidateRecord.source_user_id == UserRecord.id)
        .join(SceneRecord, MemoryCandidateRecord.source_scene_id == SceneRecord.id)
        .where(MemoryCandidateRecord.status == filters.status)
    )
    if filters.candidate_ids:
        statement = statement.where(MemoryCandidateRecord.id.in_(filters.candidate_ids))
    if filters.memory_type:
        statement = statement.where(MemoryCandidateRecord.memory_type == filters.memory_type)
    if filters.user_id:
        statement = statement.where(UserRecord.platform_user_id == filters.user_id)
    if filters.group_id:
        statement = statement.where(
            SceneRecord.scene_type == "group",
            SceneRecord.scene_id == filters.group_id,
        )
    if filters.min_confidence > 0:
        statement = statement.where(MemoryCandidateRecord.confidence >= filters.min_confidence)

    statement = statement.order_by(MemoryCandidateRecord.created_at.asc()).limit(filters.limit)
    rows = list(session.execute(statement).all())
    existing_by_user = load_existing_memories(session, {row[1].id for row in rows})
    return [
        CandidateReviewRow(
            candidate=candidate,
            user=user,
            scene=scene,
            existing_memories=tuple(existing_by_user.get(user.id, [])),
        )
        for candidate, user, scene in rows
    ]


def load_existing_memory_keys(
    session: Session,
    user_ids: set[int],
) -> set[tuple[int, str, str]]:
    if not user_ids:
        return set()
    statement = (
        select(
            MemoryRecord.user_id,
            MemoryRecord.memory_type,
            MemoryRecord.normalized_text,
        )
        .where(
            MemoryRecord.user_id.in_(user_ids),
            MemoryRecord.status == MEMORY_STATUS_ACTIVE,
        )
    )
    return {
        (int(user_id), str(memory_type), str(normalized_text))
        for user_id, memory_type, normalized_text in session.execute(statement).all()
    }


def load_existing_memories(
    session: Session,
    user_ids: set[int],
) -> dict[int, list[MemoryRecord]]:
    if not user_ids:
        return {}
    statement = (
        select(MemoryRecord)
        .where(
            MemoryRecord.user_id.in_(user_ids),
            MemoryRecord.status == MEMORY_STATUS_ACTIVE,
        )
        .order_by(MemoryRecord.updated_at.desc(), MemoryRecord.id.desc())
    )
    memories_by_user: dict[int, list[MemoryRecord]] = {}
    for memory in session.scalars(statement).all():
        memories_by_user.setdefault(memory.user_id, [])
        if len(memories_by_user[memory.user_id]) < 12:
            memories_by_user[memory.user_id].append(memory)
    return memories_by_user


async def review_rows(
    rows: list[CandidateReviewRow],
    router: LLMRouter,
    batch_size: int,
    existing_keys: set[tuple[int, str, str]],
) -> list[ReviewDecision]:
    decisions: list[ReviewDecision] = []
    for batch in chunked(rows, batch_size):
        batch_decisions, existing_keys = await review_batch(batch, router, existing_keys)
        decisions.extend(batch_decisions)
    return decisions


def chunked(rows: list[CandidateReviewRow], size: int) -> list[list[CandidateReviewRow]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


async def review_batch(
    rows: list[CandidateReviewRow],
    router: LLMRouter,
    existing_keys: set[tuple[int, str, str]],
) -> tuple[list[ReviewDecision], set[tuple[int, str, str]]]:
    if not rows:
        return [], existing_keys
    prompt = build_review_prompt(rows)
    try:
        raw_reply = await router.summarize_memory(
            [
                ChatMessage(role="system", content=REVIEW_SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ]
        )
    except LLMClientError as exc:
        if len(rows) > 1:
            return await retry_review_children(rows, router, existing_keys)
        return (
            [
                ReviewDecision(
                    candidate=row.candidate,
                    action="error",
                    memory_text="",
                    memory_type=row.candidate.memory_type,
                    confidence=0.0,
                    reason=f"LLM 调用失败：{exc}",
                )
                for row in rows
            ],
            existing_keys,
        )

    parsed = parse_review_reply(raw_reply, {row.candidate.id for row in rows})
    decisions: list[ReviewDecision] = []
    updated_keys = set(existing_keys)
    for row in rows:
        data = parsed.get(row.candidate.id)
        if data is None:
            decisions.append(
                ReviewDecision(
                    candidate=row.candidate,
                    action="error",
                    memory_text="",
                    memory_type=row.candidate.memory_type,
                    confidence=0.0,
                    reason="LLM 未返回此 candidate_id",
                )
            )
            continue
        decision = build_review_decision(row, data)
        decision = apply_deterministic_review_overrides(row, decision)
        decision = normalize_review_memory_type(row, decision)
        decision = resolve_duplicate_decision(row, decision, updated_keys)
        decisions.append(decision)
        if decision.action == "approve":
            updated_keys.add(
                (
                    row.candidate.source_user_id,
                    decision.memory_type,
                    normalize_memory_text(decision.memory_text),
                )
            )
    if len(rows) > 1 and decisions and all(decision.action == "error" for decision in decisions):
        return await retry_review_children(rows, router, existing_keys)
    return decisions, updated_keys


async def retry_review_children(
    rows: list[CandidateReviewRow],
    router: LLMRouter,
    existing_keys: set[tuple[int, str, str]],
) -> tuple[list[ReviewDecision], set[tuple[int, str, str]]]:
    midpoint = max(1, len(rows) // 2)
    groups = [rows[:midpoint], rows[midpoint:]]
    decisions: list[ReviewDecision] = []
    updated_keys = set(existing_keys)
    for group in groups:
        if not group:
            continue
        child_decisions, updated_keys = await review_batch(group, router, updated_keys)
        decisions.extend(child_decisions)
    return decisions, updated_keys


def resolve_duplicate_decision(
    row: CandidateReviewRow,
    decision: ReviewDecision,
    existing_keys: set[tuple[int, str, str]],
) -> ReviewDecision:
    if decision.action != "approve":
        return decision
    key = (
        row.candidate.source_user_id,
        decision.memory_type,
        normalize_memory_text(decision.memory_text),
    )
    if not key[2]:
        return ReviewDecision(
            candidate=decision.candidate,
            action="reject",
            memory_text="",
            memory_type=decision.memory_type,
            confidence=decision.confidence,
            reason="正式记忆正文为空",
            duplicate_memory_id=decision.duplicate_memory_id,
        )
    if key in existing_keys:
        duplicate_id = find_duplicate_memory_id(
            row.existing_memories,
            decision.memory_type,
            decision.memory_text,
        )
        return ReviewDecision(
            candidate=decision.candidate,
            action="duplicate",
            memory_text="",
            memory_type=decision.memory_type,
            confidence=decision.confidence,
            reason="与已有正式记忆重复",
            duplicate_memory_id=duplicate_id,
        )
    return decision


def build_review_prompt(rows: list[CandidateReviewRow]) -> str:
    lines = [
        "请复核下面这些长期记忆候选是否应进入正式 memories。",
        f"候选数量：{len(rows)}",
        "候选列表：",
    ]
    for row in rows:
        candidate = row.candidate
        user = row.user
        scene = row.scene
        existing = [
            {
                "memory_id": memory.id,
                "type": memory.memory_type,
                "memory": memory.memory_text,
            }
            for memory in row.existing_memories
        ]
        lines.append(
            json.dumps(
                {
                    "candidate_id": candidate.id,
                    "time": format_local_time(candidate.created_at),
                    "scene": {
                        "platform": scene.platform,
                        "type": format_scene_type(scene.scene_type),
                        "id": scene.scene_id,
                    },
                    "user": {
                        "platform_user_id": user.platform_user_id,
                        "display_name": user.display_name or user.platform_user_id,
                    },
                    "candidate": {
                        "memory": candidate.candidate_memory,
                        "type": candidate.memory_type,
                        "confidence": candidate.confidence,
                        "reason": candidate.reason,
                        "source_text": candidate.source_text,
                    },
                    "existing_memories": existing,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def parse_review_reply(raw_reply: str, candidate_ids: set[int]) -> dict[int, dict]:
    try:
        data = json.loads(extract_json_array(raw_reply))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return {
            candidate_id: {
                "action": "error",
                "type": "user_fact",
                "confidence": 0.0,
                "reason": f"JSON 解析失败：{exc}",
                "memory": "",
            }
            for candidate_id in candidate_ids
        }

    if not isinstance(data, list):
        return {}

    results: dict[int, dict] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        candidate_id = normalize_candidate_id(item.get("id", item.get("candidate_id")))
        if candidate_id is None or candidate_id not in candidate_ids:
            continue
        results[candidate_id] = item
    return results


def build_review_decision(row: CandidateReviewRow, data: dict) -> ReviewDecision:
    candidate = row.candidate
    action = normalize_action(data.get("action"))
    memory_text = normalize_memory_text_for_decision(data.get("memory"), candidate)
    memory_type = normalize_memory_type(data.get("type"), candidate.memory_type)
    confidence = normalize_confidence(data.get("confidence"), fallback=candidate.confidence)
    reason = str(data.get("reason") or "").strip()[:200] or "未给出理由"

    duplicate_memory_id = find_duplicate_memory_id(row.existing_memories, memory_type, memory_text)
    if action != "approve":
        memory_text = ""

    return ReviewDecision(
        candidate=candidate,
        action=action,
        memory_text=memory_text,
        memory_type=memory_type,
        confidence=confidence,
        reason=reason,
        duplicate_memory_id=duplicate_memory_id,
    )


def apply_deterministic_review_overrides(
    row: CandidateReviewRow,
    decision: ReviewDecision,
) -> ReviewDecision:
    relationship_memory = infer_first_person_relationship_memory(row)
    if relationship_memory is None:
        return decision
    if decision.action == "approve":
        return decision
    return ReviewDecision(
        candidate=decision.candidate,
        action="approve",
        memory_text=relationship_memory,
        memory_type="relationship_fact",
        confidence=max(decision.confidence, row.candidate.confidence, 0.85),
        reason="明确关系事实",
        duplicate_memory_id=decision.duplicate_memory_id,
    )


def normalize_review_memory_type(
    row: CandidateReviewRow,
    decision: ReviewDecision,
) -> ReviewDecision:
    if decision.action != "approve":
        return decision
    if not is_stable_preference_text(
        f"{decision.memory_text} {row.candidate.source_text or ''} {row.candidate.candidate_memory or ''}"
    ):
        return decision
    return ReviewDecision(
        candidate=decision.candidate,
        action=decision.action,
        memory_text=decision.memory_text,
        memory_type="stable_preference",
        confidence=decision.confidence,
        reason=decision.reason,
        duplicate_memory_id=decision.duplicate_memory_id,
    )


def is_stable_preference_text(value: str) -> bool:
    return bool(
        re.search(
            r"(喜欢|不喜欢|更喜欢|最喜欢|希望|不希望|更希望|习惯|讨厌|偏好|"
            r"回答时|回复时|说话方式|语气|风格|别太长|不要太长|直接给结论|先给结论|"
            r"别过度展开|不要过度展开|别\s*@|不要\s*@)",
            value,
        )
    )


def infer_first_person_relationship_memory(row: CandidateReviewRow) -> str | None:
    text = (row.candidate.source_text or row.candidate.candidate_memory or "").strip()
    match = FIRST_PERSON_RELATION_PATTERN.match(text)
    if match is None:
        return None

    relation = match.group("relation").strip()
    detail = (match.group("detail") or "").strip()
    if not relation:
        return None

    subject = (row.user.display_name or row.user.platform_user_id).strip()
    relation_label, relation_name = split_relation_label_and_name(relation)
    if relation_name:
        if detail:
            memory = f"{subject}的{relation_label}{relation_name}{detail}"
        else:
            memory = f"{subject}的{relation_label}是{relation_name}"
    else:
        memory = f"{subject}的{relation}"
        if detail:
            memory += detail
    return ensure_sentence(memory)


def split_relation_label_and_name(relation: str) -> tuple[str, str]:
    for label in sorted(RELATION_LABELS, key=len, reverse=True):
        if not relation.startswith(label):
            continue
        name = relation[len(label) :].strip()
        if name and is_likely_relation_name(name):
            return label, name
    return relation, ""


def is_likely_relation_name(value: str) -> bool:
    return (
        len(value) <= 3
        or value.startswith(("小", "老", "阿"))
        or value.endswith(("老师", "总", "姐", "哥"))
    )


def ensure_sentence(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    if re.search(r"[。.!！?？]$", text):
        return text
    return f"{text}。"


def normalize_action(value: object) -> str:
    text = str(value or "").strip().lower()
    return text if text in VALID_ACTIONS else "reject"


def normalize_memory_text_for_decision(
    value: object,
    candidate: MemoryCandidateRecord,
) -> str:
    text = str(value or "").strip()
    if text:
        return text
    return (candidate.candidate_memory or "").strip()


def normalize_memory_type(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    if text in VALID_MEMORY_TYPES:
        return text
    return fallback if fallback in VALID_MEMORY_TYPES else "user_fact"


def normalize_confidence(value: object, *, fallback: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = fallback
    return max(0.0, min(number, 1.0))


def find_duplicate_memory_id(
    existing_memories: tuple[MemoryRecord, ...],
    memory_type: str,
    memory_text: str,
) -> int | None:
    normalized = normalize_memory_text(memory_text)
    if not normalized:
        return None
    for memory in existing_memories:
        if memory.memory_type != memory_type:
            continue
        if memory.normalized_text == normalized:
            return memory.id
    return None


def apply_decisions(session: Session, decisions: list[ReviewDecision]) -> ReviewStats:
    stats = ReviewStats()
    for decision in decisions:
        candidate = decision.candidate
        if decision.action == "approve":
            session.add(
                MemoryRecord(
                    source_candidate_id=candidate.id,
                    user_id=candidate.source_user_id,
                    scene_id=candidate.source_scene_id,
                    memory_text=decision.memory_text,
                    normalized_text=normalize_memory_text(decision.memory_text),
                    memory_type=decision.memory_type,
                    confidence=decision.confidence,
                    source_text=candidate.source_text,
                    source=MEMORY_SOURCE_CANDIDATE,
                    status=MEMORY_STATUS_ACTIVE,
                    merge_reason=f"LLM 复核通过：{decision.reason}",
                )
            )
            candidate.status = CANDIDATE_STATUS_APPROVED
            candidate.memory_type = decision.memory_type
            stats.approved += 1
        elif decision.action == "duplicate":
            candidate.status = CANDIDATE_STATUS_DUPLICATE
            stats.duplicates += 1
        elif decision.action == "reject":
            candidate.status = CANDIDATE_STATUS_REJECTED
            stats.rejected += 1
        else:
            # action == "error"：LLM 调用失败或没返回该 candidate_id。
            # batch 内部已做过二分重试，到这里仍失败就落到终态，避免每个整点
            # 反复重投同一条候选。候选数据保留，可在 /admin 手动改回 pending。
            candidate.status = CANDIDATE_STATUS_ERROR
            stats.errors += 1
    return stats


def normalize_memory_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[。.!！?？~～…]+$", "", text)
    return text


def format_summary(
    filters: ReviewFilters,
    rows: list[CandidateReviewRow],
    decisions: list[ReviewDecision],
    stats: ReviewStats,
) -> str:
    counts = count_actions(decisions)
    lines = [
        "",
        "候选区 LLM 复核预览" if not filters.apply else "候选区 LLM 复核完成",
        "=" * 60,
        f"模式：{'写入' if filters.apply else '只读预览'}",
        f"筛选：status={filters.status} / limit={filters.limit} / batch_size={filters.batch_size}",
        f"候选 ID：{', '.join(str(item) for item in filters.candidate_ids) if filters.candidate_ids else '未指定'}",
        f"类型：{filters.memory_type or 'all'} / 用户：{filters.user_id or 'all'} / 群：{filters.group_id or 'all'}",
        f"读取候选：{len(rows)} 条",
        (
            f"模型决策：approve={counts.get('approve', 0)} / "
            f"reject={counts.get('reject', 0)} / duplicate={counts.get('duplicate', 0)} / "
            f"error={counts.get('error', 0)}"
        ),
    ]
    if filters.apply:
        lines.append(
            f"已写入：approved={stats.approved} / rejected={stats.rejected} / duplicates={stats.duplicates} / errors={stats.errors}"
        )
    else:
        lines.append("未修改数据库。确认后加 --apply，或把 PYCHARM_APPLY 改成 True。")
    lines.append("=" * 60)
    return "\n".join(lines)


def count_actions(decisions: list[ReviewDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
    return counts


def format_decision(index: int, decision: ReviewDecision) -> str:
    candidate = decision.candidate
    lines = [
        f"[{index}] candidate_id={candidate.id} action={decision.action}",
        f"  type={decision.memory_type} confidence={decision.confidence:.2f}",
        f"  candidate={candidate.candidate_memory}",
        f"  final_memory={decision.memory_text or '(不写入)'}",
        f"  reason={decision.reason}",
    ]
    if decision.duplicate_memory_id is not None:
        lines.append(f"  duplicate_memory_id={decision.duplicate_memory_id}")
    return "\n".join(lines)


def extract_json_array(raw_reply: str) -> str:
    text = raw_reply.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError("未找到 JSON 数组")
    return text[start : end + 1]


def normalize_candidate_id(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def format_local_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


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
