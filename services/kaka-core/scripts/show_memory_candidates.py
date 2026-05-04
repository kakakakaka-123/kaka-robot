"""查看长期记忆候选区。

这是本地开发辅助脚本，只读读取 memory_candidates，不修改任何数据。
可以在 PyCharm 中直接运行，也可以在命令行运行：

    python services/kaka-core/scripts/show_memory_candidates.py
    python services/kaka-core/scripts/show_memory_candidates.py --limit 50
    python services/kaka-core/scripts/show_memory_candidates.py --status pending
    python services/kaka-core/scripts/show_memory_candidates.py --type user_fact
    python services/kaka-core/scripts/show_memory_candidates.py --group 1073224364
    python services/kaka-core/scripts/show_memory_candidates.py --user 1419825488
    python services/kaka-core/scripts/show_memory_candidates.py --date 2026-05-01
"""

from __future__ import annotations

import argparse
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

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

# PyCharm 右键运行时可以直接改这里，不需要去找 Parameters。
#
# 可用关键词：
# --limit N              显示最近 N 条候选，默认 20。
# --status 状态          默认 pending；可用 all 查看全部。
# --type 类型            例如 user_fact / relationship_fact / important_event / stable_preference。
# --group 群号           只看某个 QQ 群。
# --user QQ号            只看某个 QQ 用户。
# --date YYYY-MM-DD      只看某一天产生的候选，按北京时间理解。
# --private              只看私聊。
# --group-chat           只看群聊。
#
# PyCharm 简单模式：只改这里，再右键运行脚本。
# 已经在数据库可视化软件里看到 memory_candidates.id 时，优先填 PYCHARM_CANDIDATE_IDS。
# 多个 ID 用英文逗号隔开，例如 "12,13,14"。
PYCHARM_CANDIDATE_IDS = ""
PYCHARM_LIMIT = 20
PYCHARM_STATUS = ""  # 留空时：未填 ID 默认 pending；填了 ID 默认 all。
PYCHARM_MEMORY_TYPE = ""
PYCHARM_GROUP_ID = ""
PYCHARM_USER_ID = ""
PYCHARM_DATE = ""
PYCHARM_PRIVATE = False
PYCHARM_GROUP_CHAT = False

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


@dataclass(frozen=True)
class CandidateFilters:
    limit: int
    candidate_ids: tuple[int, ...] = ()
    status: str | None = "pending"
    memory_type: str | None = None
    group_id: str | None = None
    user_id: str | None = None
    target_date: date | None = None
    scene_type: str | None = None


def main() -> None:
    args = parse_args()
    filters = build_filters(args)

    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        rows = load_memory_candidates(session, filters)

    if not rows:
        print("暂无符合条件的记忆候选。")
        return

    print(format_filter_summary(filters))
    for index, row in enumerate(rows, start=1):
        print(format_candidate(index, row))


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(None)
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    args = ["--limit", str(PYCHARM_LIMIT)]
    ids_text = PYCHARM_CANDIDATE_IDS.strip()
    if ids_text:
        args.extend(["--ids", ids_text])

    status = PYCHARM_STATUS.strip()
    if status:
        args.extend(["--status", status])
    elif ids_text:
        args.extend(["--status", "all"])

    memory_type = PYCHARM_MEMORY_TYPE.strip()
    if memory_type:
        args.extend(["--type", memory_type])
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
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看卡咔长期记忆候选区。")
    parser.add_argument("--id", dest="candidate_ids", action="append", type=int, help="指定单个候选 ID，可重复传入。")
    parser.add_argument("--ids", help="逗号分隔的候选 ID 列表，例如 12,13,14。")
    parser.add_argument("--limit", type=int, default=20, help="显示最近多少条，默认 20。")
    parser.add_argument("--status", default="pending", help="候选状态，默认 pending；用 all 查看全部。")
    parser.add_argument("--type", dest="memory_type", help="按记忆类型筛选。")
    parser.add_argument("--group", dest="group_id", help="只看指定 QQ 群号。")
    parser.add_argument("--user", dest="user_id", help="只看指定 QQ 用户。")
    parser.add_argument("--date", dest="target_date", help="只看指定日期，格式为 YYYY-MM-DD，按北京时间理解。")
    scene_group = parser.add_mutually_exclusive_group()
    scene_group.add_argument("--private", action="store_true", help="只看私聊。")
    scene_group.add_argument("--group-chat", action="store_true", help="只看群聊。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> CandidateFilters:
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

    status = normalize_optional_value(args.status)
    if status == "all":
        status = None

    return CandidateFilters(
        limit=args.limit,
        candidate_ids=parse_candidate_ids(args.candidate_ids, args.ids),
        status=status,
        memory_type=normalize_optional_value(args.memory_type),
        group_id=normalize_optional_value(args.group_id),
        user_id=normalize_optional_value(args.user_id),
        target_date=target_date,
        scene_type=scene_type,
    )


def normalize_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def load_memory_candidates(session: Session, filters: CandidateFilters) -> list[tuple]:
    statement = (
        select(MemoryCandidateRecord, InputRecord, UserRecord, SceneRecord)
        .join(InputRecord, MemoryCandidateRecord.source_input_id == InputRecord.id)
        .join(UserRecord, MemoryCandidateRecord.source_user_id == UserRecord.id)
        .join(SceneRecord, MemoryCandidateRecord.source_scene_id == SceneRecord.id)
    )

    if filters.candidate_ids:
        statement = statement.where(MemoryCandidateRecord.id.in_(filters.candidate_ids))

    if filters.status:
        statement = statement.where(MemoryCandidateRecord.status == filters.status)

    if filters.memory_type:
        statement = statement.where(MemoryCandidateRecord.memory_type == filters.memory_type)

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
            MemoryCandidateRecord.created_at >= start_utc,
            MemoryCandidateRecord.created_at < end_utc,
        )

    statement = statement.order_by(MemoryCandidateRecord.created_at.desc()).limit(filters.limit)
    return list(session.execute(statement).all())


def format_filter_summary(filters: CandidateFilters) -> str:
    parts = [f"limit={filters.limit}"]
    if filters.candidate_ids:
        parts.append(f"id={','.join(str(item) for item in filters.candidate_ids)}")
    if filters.status:
        parts.append(f"status={filters.status}")
    else:
        parts.append("status=all")
    if filters.memory_type:
        parts.append(f"type={filters.memory_type}")
    if filters.group_id:
        parts.append(f"group={filters.group_id}")
    if filters.user_id:
        parts.append(f"user={filters.user_id}")
    if filters.target_date:
        parts.append(f"date={filters.target_date.isoformat()}")
    if filters.scene_type:
        parts.append(f"scene={format_scene_type(filters.scene_type)}")
    return "筛选条件：" + " / ".join(parts) + "\n"


def format_candidate(index: int, row: tuple) -> str:
    candidate, input_record, user, scene = row
    display_name = user.display_name or user.platform_user_id
    scene_label = format_scene(scene)

    return "\n".join(
        [
            f"[{index}] candidate_id={candidate.id}  input_id={input_record.id}  {format_local_time(candidate.created_at)}",
            f"状态：{candidate.status} / 类型：{candidate.memory_type} / 置信度：{candidate.confidence:.2f}",
            f"场景：{scene_label}",
            f"用户：{display_name}（{user.platform_user_id}）",
            f"候选记忆：{candidate.candidate_memory}",
            f"来源消息：{candidate.source_text or '(空文本)'}",
            f"理由：{candidate.reason}",
            f"模型：{candidate.analysis_model} / prompt={candidate.analysis_prompt_version}",
            "",
        ]
    )


def format_local_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


def local_date_to_utc_range(value: date) -> tuple[datetime, datetime]:
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
