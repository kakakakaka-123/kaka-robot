"""查看最近对话记录。

这是本地开发辅助脚本，只读读取数据库，不修改任何数据。
可以在 PyCharm 中直接运行，也可以在命令行运行：

    python services/kaka-core/scripts/show_recent_conversations.py
    python services/kaka-core/scripts/show_recent_conversations.py --limit 50
    python services/kaka-core/scripts/show_recent_conversations.py --group 1073224364
    python services/kaka-core/scripts/show_recent_conversations.py --user 1419825488
    python services/kaka-core/scripts/show_recent_conversations.py --date 2026-05-01
    python services/kaka-core/scripts/show_recent_conversations.py --replied-only
    python services/kaka-core/scripts/show_recent_conversations.py --observed-only
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
    OutputRecord,
    SceneRecord,
    UserRecord,
)

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")

# PyCharm 右键运行时可以直接改这里，不需要去找 Parameters。
#
# 可用关键词：
# --limit N              显示最近 N 条，默认 20。
# --group 群号           只看某个 QQ 群。
# --user QQ号            只看某个 QQ 用户。
# --date YYYY-MM-DD      只看某一天，按北京时间理解。
# --private              只看私聊。
# --group-chat           只看群聊。
# --replied-only         只看卡咔回复过的消息，也就是有 outputs 的记录。
# --observed-only        只看普通观察记录，也就是没有 outputs 的记录。
# --origin 来源          按输出来源筛选，例如 passive / active / system。
# --reason 原因          按输出原因筛选，例如 private / mention / keyword。
#
# PyCharm 简单模式：只改这里，再右键运行脚本。
# 已经在数据库可视化软件里看到 inputs.id 时，优先填 PYCHARM_INPUT_IDS。
# 多个 ID 用英文逗号隔开，例如 "12,13,14"。
PYCHARM_INPUT_IDS = ""
PYCHARM_LIMIT = 10
PYCHARM_GROUP_ID = ""
PYCHARM_USER_ID = ""
PYCHARM_DATE = ""
PYCHARM_PRIVATE = False
PYCHARM_GROUP_CHAT = False
PYCHARM_REPLIED_ONLY = False
PYCHARM_OBSERVED_ONLY = False
PYCHARM_OUTPUT_ORIGIN = ""
PYCHARM_OUTPUT_REASON = ""

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


@dataclass(frozen=True)
class ConversationFilters:
    limit: int
    input_ids: tuple[int, ...] = ()
    group_id: str | None = None
    user_id: str | None = None
    target_date: date | None = None
    scene_type: str | None = None
    replied_only: bool = False
    observed_only: bool = False
    output_origin: str | None = None
    output_reason: str | None = None


def main() -> None:
    args = parse_args()
    filters = build_filters(args)

    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        rows = load_recent_conversations(session, filters)

    if not rows:
        print("暂无符合条件的对话记录。")
        return

    print(format_filter_summary(filters))
    for index, row in enumerate(rows, start=1):
        print(format_conversation(index, row))


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

    if PYCHARM_REPLIED_ONLY and PYCHARM_OBSERVED_ONLY:
        raise SystemExit("PYCHARM_REPLIED_ONLY 和 PYCHARM_OBSERVED_ONLY 不能同时为 True。")
    if PYCHARM_REPLIED_ONLY:
        args.append("--replied-only")
    if PYCHARM_OBSERVED_ONLY:
        args.append("--observed-only")

    output_origin = PYCHARM_OUTPUT_ORIGIN.strip()
    if output_origin:
        args.extend(["--origin", output_origin])
    output_reason = PYCHARM_OUTPUT_REASON.strip()
    if output_reason:
        args.extend(["--reason", output_reason])
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="查看卡咔最近对话记录。")
    parser.add_argument("--id", dest="input_ids", action="append", type=int, help="指定单个输入 ID，可重复传入。")
    parser.add_argument("--ids", help="逗号分隔的输入 ID 列表，例如 12,13,14。")
    parser.add_argument("--limit", type=int, default=20, help="显示最近多少条，默认 20。")
    parser.add_argument("--group", dest="group_id", help="只看指定 QQ 群号。")
    parser.add_argument("--user", dest="user_id", help="只看指定 QQ 用户。")
    parser.add_argument("--date", dest="target_date", help="只看指定日期，格式为 YYYY-MM-DD，按北京时间理解。")
    scene_group = parser.add_mutually_exclusive_group()
    scene_group.add_argument("--private", action="store_true", help="只看私聊。")
    scene_group.add_argument("--group-chat", action="store_true", help="只看群聊。")
    reply_group = parser.add_mutually_exclusive_group()
    reply_group.add_argument("--replied-only", action="store_true", help="只看卡咔实际回复过的消息。")
    reply_group.add_argument("--observed-only", action="store_true", help="只看普通观察消息。")
    parser.add_argument("--origin", dest="output_origin", help="按输出来源筛选，例如 passive / active / system。")
    parser.add_argument("--reason", dest="output_reason", help="按输出原因筛选，例如 private / mention / keyword。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> ConversationFilters:
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

    return ConversationFilters(
        limit=args.limit,
        input_ids=parse_input_ids(args.input_ids, args.ids),
        group_id=normalize_optional_id(args.group_id),
        user_id=normalize_optional_id(args.user_id),
        target_date=target_date,
        scene_type=scene_type,
        replied_only=args.replied_only,
        observed_only=args.observed_only,
        output_origin=normalize_optional_id(args.output_origin),
        output_reason=normalize_optional_id(args.output_reason),
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


def load_recent_conversations(session: Session, filters: ConversationFilters) -> list[tuple]:
    statement = (
        select(InputRecord, UserRecord, SceneRecord, OutputRecord)
        .join(UserRecord, InputRecord.user_id == UserRecord.id)
        .join(SceneRecord, InputRecord.scene_id == SceneRecord.id)
        .outerjoin(OutputRecord, OutputRecord.input_id == InputRecord.id)
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

    if filters.replied_only:
        statement = statement.where(OutputRecord.id.is_not(None))

    if filters.observed_only:
        statement = statement.where(OutputRecord.id.is_(None))

    if filters.output_origin:
        statement = statement.where(OutputRecord.output_origin == filters.output_origin)

    if filters.output_reason:
        statement = statement.where(OutputRecord.output_reason == filters.output_reason)

    if filters.target_date:
        start_utc, end_utc = local_date_to_utc_range(filters.target_date)
        statement = statement.where(
            InputRecord.created_at >= start_utc,
            InputRecord.created_at < end_utc,
        )

    statement = statement.order_by(InputRecord.created_at.desc()).limit(filters.limit)
    return list(session.execute(statement).all())


def format_filter_summary(filters: ConversationFilters) -> str:
    parts = [f"limit={filters.limit}"]
    if filters.input_ids:
        parts.append(f"id={','.join(str(item) for item in filters.input_ids)}")
    if filters.group_id:
        parts.append(f"group={filters.group_id}")
    if filters.user_id:
        parts.append(f"user={filters.user_id}")
    if filters.target_date:
        parts.append(f"date={filters.target_date.isoformat()}")
    if filters.scene_type:
        parts.append(f"scene={format_scene_type(filters.scene_type)}")
    if filters.replied_only:
        parts.append("只看已回复")
    if filters.observed_only:
        parts.append("只看观察记录")
    if filters.output_origin:
        parts.append(f"origin={filters.output_origin}")
    if filters.output_reason:
        parts.append(f"reason={filters.output_reason}")
    return "筛选条件：" + " / ".join(parts) + "\n"


def format_conversation(index: int, row: tuple) -> str:
    input_record, user, scene, output = row
    local_time = format_local_time(input_record.created_at)
    scene_label = format_scene(scene)
    display_name = user.display_name or user.platform_user_id
    reply_text = output.content_text if output and output.content_text else "(无回复)"
    status = format_input_status(input_record, output)

    return "\n".join(
        [
            f"[{index}] input_id={input_record.id}  {local_time}  {scene_label}  {status}",
            f"用户：{display_name}（{user.platform_user_id}）",
            f"用户消息：{input_record.content_text or '(空文本)'}",
            f"卡咔回复：{reply_text}",
            "",
        ]
    )


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


def format_input_status(input_record: InputRecord, output: OutputRecord | None) -> str:
    if output is not None:
        if output.should_reply:
            return f"已回复 / {output.output_origin}.{output.output_reason}"
        reason = output.no_reply_reason or "no_reply"
        return f"已决策未回复 / {output.output_origin}.{output.output_reason}.{reason}"
    return f"观察 / analysis={input_record.analysis_status}"


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
