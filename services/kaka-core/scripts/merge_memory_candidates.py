"""把候选区合并到正式长期记忆表。

默认只做预览，不修改数据库。确认结果后加 --apply 才会写入 memories，
并把成功合并的候选标记为 approved，把重复候选标记为 merged_duplicate。

如果已经在数据库可视化软件里看过 `memory_candidates.id`，PyCharm 右键运行时
优先改下面的简单配置：

    PYCHARM_CANDIDATE_IDS = "12,13"
    PYCHARM_APPLY = False

命令行示例：

    python services/kaka-core/scripts/merge_memory_candidates.py
    python services/kaka-core/scripts/merge_memory_candidates.py --limit 50
    python services/kaka-core/scripts/merge_memory_candidates.py --ids 12,13 --apply
    python services/kaka-core/scripts/merge_memory_candidates.py --type user_fact
    python services/kaka-core/scripts/merge_memory_candidates.py --apply
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "kaka-core" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaka_core.memory.merge import (  # noqa: E402
    CANDIDATE_STATUS_PENDING,
    MergeDecision,
    MergeFilters,
    MergeStats,
    apply_decisions,
    build_merge_decisions,
    count_actions,
    load_candidates,
)
from kaka_core.storage.database import create_session_factory, init_database  # noqa: E402

# PyCharm 简单模式：只改这里，再右键运行脚本。
# 多个候选 ID 用英文逗号隔开，例如 "12,13,14"。
# 不填 ID 时按 limit 预览 pending 候选。
PYCHARM_CANDIDATE_IDS = ""
PYCHARM_LIMIT = 20
PYCHARM_MEMORY_TYPE = ""
PYCHARM_MIN_CONFIDENCE = 0.0
PYCHARM_APPLY = False

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


def main() -> None:
    args = parse_args()
    filters = build_filters(args)

    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        candidates = load_candidates(session, filters)
        decisions = build_merge_decisions(session, candidates)
        stats = apply_decisions(session, decisions) if filters.apply else MergeStats()
        if filters.apply:
            session.commit()

    print(format_summary(filters, candidates, decisions, stats))
    for index, decision in enumerate(decisions, start=1):
        print(format_decision(index, decision))


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
    memory_type = PYCHARM_MEMORY_TYPE.strip()
    if memory_type:
        args.extend(["--type", memory_type])
    if PYCHARM_MIN_CONFIDENCE > 0:
        args.extend(["--min-confidence", str(PYCHARM_MIN_CONFIDENCE)])
    if PYCHARM_APPLY:
        args.append("--apply")
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把记忆候选合并到正式 memories 表。")
    parser.add_argument("--id", dest="candidate_ids", action="append", type=int, help="指定单个候选 ID，可重复传入。")
    parser.add_argument("--ids", help="逗号分隔的候选 ID 列表，例如 12,13,14。")
    parser.add_argument("--limit", type=int, default=20, help="处理最近多少条候选，默认 20。")
    parser.add_argument("--status", default=CANDIDATE_STATUS_PENDING, help="候选状态，默认 pending。")
    parser.add_argument("--type", dest="memory_type", help="按记忆类型筛选。")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="最低置信度，默认 0。")
    parser.add_argument("--apply", action="store_true", help="真正写入 memories 并更新候选状态。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> MergeFilters:
    if args.limit <= 0:
        raise SystemExit("--limit 必须大于 0。")
    if args.min_confidence < 0 or args.min_confidence > 1:
        raise SystemExit("--min-confidence 必须在 0 到 1 之间。")
    return MergeFilters(
        limit=args.limit,
        candidate_ids=parse_candidate_ids(args.candidate_ids, args.ids),
        status=normalize_required_value(args.status),
        memory_type=normalize_optional_value(args.memory_type),
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


def format_summary(
    filters: MergeFilters,
    candidates: list,
    decisions: list[MergeDecision],
    stats: MergeStats,
) -> str:
    action_counts = count_actions(decisions)
    lines = [
        "",
        "候选区合并预览" if not filters.apply else "候选区合并完成",
        "=" * 60,
        f"模式：{'写入' if filters.apply else '只读预览'}",
        f"筛选：status={filters.status} / limit={filters.limit}",
        f"候选 ID：{', '.join(str(item) for item in filters.candidate_ids) if filters.candidate_ids else '未指定'}",
        f"候选类型：{filters.memory_type or 'all'}",
        f"最低置信度：{filters.min_confidence:.2f}",
        f"读取候选：{len(candidates)} 条",
        f"计划：insert={action_counts.get('insert', 0)} / duplicate={action_counts.get('duplicate', 0)} / skip={action_counts.get('skip', 0)}",
    ]
    if filters.apply:
        lines.append(
            f"已写入：inserted={stats.inserted} / duplicates={stats.duplicates} / skipped={stats.skipped}"
        )
    else:
        lines.append("未修改数据库。确认后加 --apply，或把 PYCHARM_APPLY 改成 True。")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_decision(index: int, decision: MergeDecision) -> str:
    candidate = decision.candidate
    lines = [
        f"[{index}] candidate_id={candidate.id} action={decision.action}",
        f"  type={candidate.memory_type} confidence={candidate.confidence:.2f}",
        f"  memory={candidate.candidate_memory}",
        f"  reason={decision.reason}",
    ]
    if decision.duplicate_memory_id is not None:
        lines.append(f"  duplicate_memory_id={decision.duplicate_memory_id}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
