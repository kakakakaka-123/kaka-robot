"""管理正式长期记忆。

这是本地开发辅助脚本，只读预览时不会修改数据库。
日常更推荐把不合适的记忆先归档为 `archived`，确认错误、垃圾或敏感时再硬删除。

PyCharm 右键运行时，优先改下面的简单配置：

    PYCHARM_MEMORY_IDS = "12"
    PYCHARM_ACTION = "archive"
    PYCHARM_APPLY = False

常用动作：

    archive   归档记忆，保留记录，但不再参与回复检索。
    restore   恢复记忆，把 archived 改回 active。
    delete    硬删除记忆，只用于确认错误、垃圾或敏感内容。

安全规则：

    PYCHARM_APPLY = False 时只预览，不写数据库。
    PYCHARM_ACTION = "delete" 且 PYCHARM_APPLY = True 时，还必须把
    PYCHARM_CONFIRM_DELETE 改成 True。

命令行参数仍然可用：

    --id 12
    --ids 12,13,14
    --status active|archived
    --delete
    --apply
    --yes
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "kaka-core" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaka_core.storage.database import create_session_factory, init_database  # noqa: E402
from kaka_core.storage.models import MemoryRecord  # noqa: E402

VALID_TARGET_STATUSES = {"active", "archived"}
PYCHARM_ACTIONS = {"archive", "restore", "delete"}

# PyCharm 简单模式：只改这里，再右键运行脚本。
# 例子：
#   PYCHARM_MEMORY_IDS = "12"
#   PYCHARM_ACTION = "archive"
#   PYCHARM_APPLY = True
#
# 多个 ID 用英文逗号隔开，例如 "12,13,14"。
# 默认不填 ID、不写库，避免误操作。
PYCHARM_MEMORY_IDS = ""
PYCHARM_ACTION = "archive"  # archive / restore / delete
PYCHARM_APPLY = False
PYCHARM_CONFIRM_DELETE = False

# 高级模式：如果你更习惯命令行参数，可以直接在这里写参数列表。
# 非空时会覆盖上面的简单模式；外部真实命令行参数仍然优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


@dataclass(frozen=True)
class ManageFilters:
    memory_ids: tuple[int, ...]
    target_status: str | None = None
    delete: bool = False
    apply: bool = False
    yes: bool = False


@dataclass(frozen=True)
class ManageDecision:
    memory_id: int
    action: str
    before_status: str
    after_status: str | None
    memory_text: str
    normalized_text: str
    memory_type: str


def main() -> None:
    configure_console_output()
    args = parse_args()
    filters = build_filters(args)
    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        memories = load_memories(session, filters.memory_ids)
        decisions = build_decisions(memories, filters)
        apply_stats = apply_decisions(session, decisions, filters)
        if filters.apply:
            session.commit()

    print(format_summary(filters, decisions, apply_stats))
    for index, decision in enumerate(decisions, start=1):
        print(format_decision(index, decision))


def configure_console_output() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(sys.argv[1:])
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    """把文件顶部的 PyCharm 简单配置转换成命令行参数。

    这样用户在可视化数据库里看到记忆 ID 后，只需要回到脚本顶部填写 ID
    和动作，不必记住 `--id / --status / --delete` 这些参数。
    """

    args: list[str] = []
    ids_text = PYCHARM_MEMORY_IDS.strip()
    if ids_text:
        args.extend(["--ids", ids_text])

    action = PYCHARM_ACTION.strip().lower()
    if action and action not in PYCHARM_ACTIONS:
        raise SystemExit(
            "PYCHARM_ACTION 只能是 archive / restore / delete，"
            f"当前是: {PYCHARM_ACTION}"
        )
    if action == "archive":
        args.extend(["--status", "archived"])
    elif action == "restore":
        args.extend(["--status", "active"])
    elif action == "delete":
        args.append("--delete")

    if PYCHARM_APPLY:
        args.append("--apply")
    if PYCHARM_CONFIRM_DELETE:
        args.append("--yes")
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="管理正式长期记忆。")
    parser.add_argument("--id", dest="memory_ids", action="append", type=int, help="单个记忆 ID，可重复传入。")
    parser.add_argument(
        "--ids",
        help="逗号分隔的记忆 ID 列表，例如 1,2,3。",
    )
    parser.add_argument(
        "--status",
        dest="target_status",
        choices=sorted(VALID_TARGET_STATUSES),
        help="把记忆切换到指定状态：active / archived。",
    )
    parser.add_argument("--delete", action="store_true", help="硬删除指定记忆。")
    parser.add_argument("--apply", action="store_true", help="真正写入数据库。")
    parser.add_argument("--yes", action="store_true", help="允许执行硬删除。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> ManageFilters:
    memory_ids = parse_memory_ids(args.memory_ids, args.ids)
    if not memory_ids:
        raise SystemExit("至少要指定一个 memory_id。")
    if args.delete and args.target_status is not None:
        raise SystemExit("--delete 和 --status 不能同时使用。")
    if not args.delete and args.target_status is None:
        raise SystemExit("必须指定 --status active|archived 或 --delete。")
    if args.delete and args.apply and not args.yes:
        raise SystemExit("硬删除写入数据库时需要额外传入 --yes。")
    return ManageFilters(
        memory_ids=memory_ids,
        target_status=args.target_status,
        delete=bool(args.delete),
        apply=bool(args.apply),
        yes=bool(args.yes),
    )


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
    # 保留顺序并去重
    seen: set[int] = set()
    unique: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)


def load_memories(session: Session, memory_ids: tuple[int, ...]) -> list[MemoryRecord]:
    if not memory_ids:
        return []
    statement = (
        select(MemoryRecord)
        .where(MemoryRecord.id.in_(memory_ids))
        .order_by(MemoryRecord.id.asc())
    )
    return list(session.scalars(statement).all())


def build_decisions(memories: list[MemoryRecord], filters: ManageFilters) -> list[ManageDecision]:
    memory_by_id = {memory.id: memory for memory in memories}
    decisions: list[ManageDecision] = []
    for memory_id in filters.memory_ids:
        memory = memory_by_id.get(memory_id)
        if memory is None:
            decisions.append(
                ManageDecision(
                    memory_id=memory_id,
                    action="missing",
                    before_status="not_found",
                    after_status=None,
                    memory_text="",
                    normalized_text="",
                    memory_type="",
                )
            )
            continue
        if filters.delete:
            decisions.append(
                ManageDecision(
                    memory_id=memory.id,
                    action="delete",
                    before_status=memory.status,
                    after_status=None,
                    memory_text=memory.memory_text,
                    normalized_text=memory.normalized_text,
                    memory_type=memory.memory_type,
                )
            )
            continue
        target_status = filters.target_status or memory.status
        if target_status not in VALID_TARGET_STATUSES:
            raise SystemExit(f"不支持的状态: {target_status}")
        decisions.append(
            ManageDecision(
                memory_id=memory.id,
                action="update" if memory.status != target_status else "noop",
                before_status=memory.status,
                after_status=target_status,
                memory_text=memory.memory_text,
                normalized_text=memory.normalized_text,
                memory_type=memory.memory_type,
            )
        )
    return decisions


@dataclass
class ApplyStats:
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    missing: int = 0


def apply_decisions(session: Session, decisions: list[ManageDecision], filters: ManageFilters) -> ApplyStats:
    stats = ApplyStats()
    for decision in decisions:
        memory = session.get(MemoryRecord, decision.memory_id)
        if memory is None:
            stats.missing += 1
            continue
        if decision.action == "missing":
            stats.missing += 1
            continue
        if decision.action == "noop":
            stats.skipped += 1
            continue
        if not filters.apply:
            continue
        if decision.action == "delete":
            if not filters.yes:
                raise SystemExit("硬删除需要 --yes。")
            session.delete(memory)
            stats.deleted += 1
            continue
        if decision.action == "update" and decision.after_status is not None:
            memory.status = decision.after_status
            memory.updated_at = utc_now()
            stats.updated += 1
    return stats


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_summary(filters: ManageFilters, decisions: list[ManageDecision], stats: ApplyStats) -> str:
    counts = count_decision_actions(decisions)
    lines = [
        "",
        "正式记忆管理预览" if not filters.apply else "正式记忆管理完成",
        "=" * 60,
        f"模式：{'写入' if filters.apply else '只读预览'}",
        f"目标：{', '.join(str(item) for item in filters.memory_ids)}",
        f"动作：{'delete' if filters.delete else filters.target_status}",
    ]
    if not filters.apply:
        lines.append(
            "计划："
            f"update={counts.get('update', 0)} / "
            f"delete={counts.get('delete', 0)} / "
            f"noop={counts.get('noop', 0)} / "
            f"missing={counts.get('missing', 0)}"
        )
        lines.append("未修改数据库；确认后加 --apply，或把 PYCHARM_APPLY 改成 True。")
    else:
        lines.append(
            f"结果：update={stats.updated} / delete={stats.deleted} / "
            f"skip={stats.skipped} / missing={stats.missing}"
        )
    lines.append("=" * 60)
    return "\n".join(lines)


def count_decision_actions(decisions: list[ManageDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
    return counts


def format_decision(index: int, decision: ManageDecision) -> str:
    lines = [
        f"[{index}] memory_id={decision.memory_id} action={decision.action}",
        f"  before_status={decision.before_status}",
    ]
    if decision.after_status is not None:
        lines.append(f"  after_status={decision.after_status}")
    lines.extend(
        [
            f"  type={decision.memory_type}",
            f"  text={decision.memory_text or '(missing)'}",
            f"  normalized={decision.normalized_text or '(missing)'}",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
