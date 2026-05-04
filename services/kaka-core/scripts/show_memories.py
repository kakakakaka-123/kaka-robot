"""查看正式长期记忆。

这是本地开发辅助脚本，只读读取 memories，不修改任何数据。
可以在 PyCharm 中直接运行，也可以在命令行运行：

    python services/kaka-core/scripts/show_memories.py
    python services/kaka-core/scripts/show_memories.py --limit 50
    python services/kaka-core/scripts/show_memories.py --status active
    python services/kaka-core/scripts/show_memories.py --status all
    python services/kaka-core/scripts/show_memories.py --type user_fact
    python services/kaka-core/scripts/show_memories.py --source candidate
    python services/kaka-core/scripts/show_memories.py --group 1073224364
    python services/kaka-core/scripts/show_memories.py --user 1419825488
    python services/kaka-core/scripts/show_memories.py --date 2026-05-01
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
    MemoryCandidateRecord,
    MemoryRecord,
    SceneRecord,
    UserRecord,
)

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

# PyCharm 右键运行时可以直接改这里，不需要去找 Parameters。
#
# 可用关键词：
# --limit N              显示最近 N 条正式记忆，默认 20。
# --status 状态          默认 active；可用 all 查看全部。
# --type 类型            例如 user_fact / relationship_fact / important_event / stable_preference。
# --source 来源          例如 candidate。
# --group 群号           只看某个 QQ 群来源的记忆。
# --user QQ号            只看某个 QQ 用户的记忆。
# --date YYYY-MM-DD      只看某一天合并出的正式记忆，按北京时间理解。
# --private              只看私聊来源的记忆。
# --group-chat           只看群聊来源的记忆。
#
# PyCharm 简单模式：只改这里，再右键运行脚本。
# 已经在数据库可视化软件里看到 memories.id 时，优先填 PYCHARM_MEMORY_IDS。
# 多个 ID 用英文逗号隔开，例如 "12,13,14"。
PYCHARM_MEMORY_IDS = ""
PYCHARM_LIMIT = 20
PYCHARM_STATUS = ""  # 留空时：未填 ID 默认 active；填了 ID 默认 all。
PYCHARM_MEMORY_TYPE = ""
PYCHARM_SOURCE = ""
PYCHARM_GROUP_ID = ""
PYCHARM_USER_ID = ""
PYCHARM_DATE = ""
PYCHARM_PRIVATE = False
PYCHARM_GROUP_CHAT = False

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


@dataclass(frozen=True)
class MemoryFilters:
    limit: int
    memory_ids: tuple[int, ...] = ()
    status: str | None = "active"
    memory_type: str | None = None
    source: str | None = None
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
        rows = load_memories(session, filters)

    if not rows:
        print("暂无符合条件的正式记忆。")
        return

    print(format_filter_summary(filters))
    for index, row in enumerate(rows, start=1):
        print(format_memory(index, row))


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(None)
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    args = ["--limit", str(PYCHARM_LIMIT)]
    ids_text = PYCHARM_MEMORY_IDS.strip()
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
    source = PYCHARM_SOURCE.strip()
    if source:
        args.extend(["--source", source])
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
    parser = argparse.ArgumentParser(description="查看卡咔正式长期记忆。")
    parser.add_argument("--id", dest="memory_ids", action="append", type=int, help="指定单个记忆 ID，可重复传入。")
    parser.add_argument("--ids", help="逗号分隔的记忆 ID 列表，例如 12,13,14。")
    parser.add_argument("--limit", type=int, default=20, help="显示最近多少条，默认 20。")
    parser.add_argument("--status", default="active", help="记忆状态，默认 active；用 all 查看全部。")
    parser.add_argument("--type", dest="memory_type", help="按记忆类型筛选。")
    parser.add_argument("--source", dest="source", help="按记忆来源筛选，例如 candidate。")
    parser.add_argument("--group", dest="group_id", help="只看指定 QQ 群号。")
    parser.add_argument("--user", dest="user_id", help="只看指定 QQ 用户。")
    parser.add_argument("--date", dest="target_date", help="只看指定日期，格式为 YYYY-MM-DD，按北京时间理解。")
    scene_group = parser.add_mutually_exclusive_group()
    scene_group.add_argument("--private", action="store_true", help="只看私聊来源。")
    scene_group.add_argument("--group-chat", action="store_true", help="只看群聊来源。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> MemoryFilters:
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

    return MemoryFilters(
        limit=args.limit,
        memory_ids=parse_memory_ids(args.memory_ids, args.ids),
        status=status,
        memory_type=normalize_optional_value(args.memory_type),
        source=normalize_optional_value(args.source),
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


def parse_memory_ids(memory_ids: list[int] | None, ids_text: str | None) -> tuple[int, ...]:
    values: list[int] = []
    for item in memory_ids or []:
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
                raise SystemExit(f"无效的 memory_id: {piece}") from None
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


def load_memories(session: Session, filters: MemoryFilters) -> list[tuple]:
    statement = (
        select(MemoryRecord, UserRecord, SceneRecord, MemoryCandidateRecord)
        .join(UserRecord, MemoryRecord.user_id == UserRecord.id)
        .outerjoin(SceneRecord, MemoryRecord.scene_id == SceneRecord.id)
        .outerjoin(
            MemoryCandidateRecord,
            MemoryRecord.source_candidate_id == MemoryCandidateRecord.id,
        )
    )

    if filters.memory_ids:
        statement = statement.where(MemoryRecord.id.in_(filters.memory_ids))

    if filters.status:
        statement = statement.where(MemoryRecord.status == filters.status)

    if filters.memory_type:
        statement = statement.where(MemoryRecord.memory_type == filters.memory_type)

    if filters.source:
        statement = statement.where(MemoryRecord.source == filters.source)

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
            MemoryRecord.created_at >= start_utc,
            MemoryRecord.created_at < end_utc,
        )

    statement = statement.order_by(MemoryRecord.created_at.desc()).limit(filters.limit)
    return list(session.execute(statement).all())


def format_filter_summary(filters: MemoryFilters) -> str:
    parts = [f"limit={filters.limit}"]
    if filters.memory_ids:
        parts.append(f"id={','.join(str(item) for item in filters.memory_ids)}")
    if filters.status:
        parts.append(f"status={filters.status}")
    else:
        parts.append("status=all")
    if filters.memory_type:
        parts.append(f"type={filters.memory_type}")
    if filters.source:
        parts.append(f"source={filters.source}")
    if filters.group_id:
        parts.append(f"group={filters.group_id}")
    if filters.user_id:
        parts.append(f"user={filters.user_id}")
    if filters.target_date:
        parts.append(f"date={filters.target_date.isoformat()}")
    if filters.scene_type:
        parts.append(f"scene={format_scene_type(filters.scene_type)}")
    return "筛选条件：" + " / ".join(parts) + "\n"


def format_memory(index: int, row: tuple) -> str:
    memory, user, scene, candidate = row
    display_name = user.display_name or user.platform_user_id
    scene_label = format_scene(scene) if scene is not None else "(无场景)"
    candidate_id = candidate.id if candidate is not None else memory.source_candidate_id
    candidate_label = str(candidate_id) if candidate_id is not None else "-"

    return "\n".join(
        [
            (
                f"[{index}] memory_id={memory.id}  "
                f"candidate_id={candidate_label}  {format_local_time(memory.created_at)}"
            ),
            (
                f"状态：{memory.status} / 类型：{memory.memory_type} / "
                f"来源：{memory.source} / 置信度：{memory.confidence:.2f}"
            ),
            f"场景：{scene_label}",
            f"用户：{display_name}（{user.platform_user_id}）",
            f"正式记忆：{memory.memory_text}",
            f"去重文本：{memory.normalized_text}",
            f"来源消息：{memory.source_text or '(空文本)'}",
            f"合并理由：{memory.merge_reason or '(无)'}",
            f"更新时间：{format_local_time(memory.updated_at)}",
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
