"""预览正式长期记忆检索结果。

这是本地开发辅助脚本，只读读取 memories，不修改任何数据。
它使用正式的 `kaka_core.memory.search` 检索模块，因此结果应和聊天回复前的记忆检索一致。

可以在 PyCharm 中直接运行，也可以在命令行运行：

    python services/kaka-core/scripts/search_memories.py --user 1419825488 --text "我现在要继续做卡咔的记忆检索"
    python services/kaka-core/scripts/search_memories.py --user 1419825488 --group 1073224364 --text "我现在要继续做卡咔的记忆检索"
    python services/kaka-core/scripts/search_memories.py --user 1419825488 --private --text "我想继续优化回复风格"
    python services/kaka-core/scripts/search_memories.py --user 1419825488 --text "卡咔记忆" --limit 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "kaka-core" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaka_core.memory.search import (  # noqa: E402,F401
    MemorySearchResult,
    SearchFilters,
    format_local_time,
    format_scene,
    format_scene_type,
    load_memory_pool,
    load_user,
    rank_memories,
    search_user_memories,
)
from kaka_core.storage.database import create_session_factory, init_database  # noqa: E402

# PyCharm 简单模式：只改这里，再右键运行脚本。
PYCHARM_USER_ID = ""
PYCHARM_TEXT = ""
PYCHARM_GROUP_ID = ""
PYCHARM_PRIVATE = False
PYCHARM_LIMIT = 5
PYCHARM_POOL_SIZE = 300
PYCHARM_MIN_SCORE = 1.0
PYCHARM_MEMORY_TYPE = ""

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


def main() -> None:
    args = parse_args()
    filters = build_filters(args)

    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        user = load_user(session, filters)
        if user is None:
            print(f"未找到用户：{filters.platform}/{filters.user_id}")
            return
        rows = load_memory_pool(session, filters, user)
        results = rank_memories(rows, filters)

    print(format_search_summary(filters, len(rows), len(results)))
    if not results:
        print("暂无符合条件的正式记忆。")
        return

    for index, result in enumerate(results, start=1):
        print(format_search_result(index, result))


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(None)
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    args = [
        "--user",
        PYCHARM_USER_ID.strip(),
        "--text",
        PYCHARM_TEXT.strip(),
        "--limit",
        str(PYCHARM_LIMIT),
        "--pool-size",
        str(PYCHARM_POOL_SIZE),
        "--min-score",
        str(PYCHARM_MIN_SCORE),
    ]
    group_id = PYCHARM_GROUP_ID.strip()
    if group_id:
        args.extend(["--group", group_id])
    elif PYCHARM_PRIVATE:
        args.append("--private")
    memory_type = PYCHARM_MEMORY_TYPE.strip()
    if memory_type:
        args.extend(["--type", memory_type])
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="预览卡咔正式长期记忆检索结果。")
    parser.add_argument("--platform", default="qq", help="平台，默认 qq。")
    parser.add_argument("--user", dest="user_id", required=True, help="当前 QQ 用户号。")
    parser.add_argument("--text", dest="query_text", required=True, help="当前消息文本。")
    parser.add_argument("--limit", type=int, default=5, help="最多返回多少条，默认 5。")
    parser.add_argument(
        "--pool-size",
        type=int,
        default=300,
        help="最多取该用户最近多少条 active 记忆参与打分，默认 300。",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=1.0,
        help="最低返回分数，默认 1.0；调成 0 可观察低相关记忆。",
    )
    parser.add_argument("--type", dest="memory_type", help="只检索某类记忆。")
    scene_group = parser.add_mutually_exclusive_group()
    scene_group.add_argument("--group", dest="group_id", help="当前 QQ 群号。")
    scene_group.add_argument("--private", action="store_true", help="当前消息是私聊。")
    return parser.parse_args(argv)


def build_filters(args: argparse.Namespace) -> SearchFilters:
    if args.limit <= 0:
        raise SystemExit("--limit 必须大于 0。")
    if args.pool_size <= 0:
        raise SystemExit("--pool-size 必须大于 0。")

    user_id = normalize_required_text(args.user_id, "--user")
    query_text = normalize_required_text(args.query_text, "--text")

    target_scene_type = None
    target_scene_id = None
    group_id = normalize_optional_value(args.group_id)
    if group_id:
        target_scene_type = "group"
        target_scene_id = group_id
    elif args.private:
        target_scene_type = "private"
        target_scene_id = user_id

    return SearchFilters(
        platform=normalize_optional_value(args.platform) or "qq",
        user_id=user_id,
        query_text=query_text,
        limit=args.limit,
        pool_size=args.pool_size,
        min_score=args.min_score,
        memory_type=normalize_optional_value(args.memory_type),
        target_scene_type=target_scene_type,
        target_scene_id=target_scene_id,
    )


def normalize_required_text(value: str | None, name: str) -> str:
    text = normalize_optional_value(value)
    if text is None:
        raise SystemExit(f"{name} 不能为空。")
    return text


def normalize_optional_value(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def format_search_summary(filters: SearchFilters, pool_count: int, result_count: int) -> str:
    parts = [
        f"platform={filters.platform}",
        f"user={filters.user_id}",
        f"limit={filters.limit}",
        f"pool_size={filters.pool_size}",
        f"min_score={filters.min_score:g}",
    ]
    if filters.memory_type:
        parts.append(f"type={filters.memory_type}")
    if filters.target_scene_type and filters.target_scene_id:
        parts.append(f"scene={format_scene_type(filters.target_scene_type)}:{filters.target_scene_id}")

    return "\n".join(
        [
            "记忆检索预览",
            "=" * 60,
            "说明：只读读取 memories，不修改数据库；聊天回复接入后会复用同一套检索逻辑。",
            "筛选条件：" + " / ".join(parts),
            f"当前消息：{filters.query_text}",
            f"候选池：{pool_count} 条 active 记忆；返回：{result_count} 条。",
            "",
        ]
    )


def format_search_result(index: int, result: MemorySearchResult) -> str:
    memory = result.memory
    scene_label = format_scene(result.scene) if result.scene is not None else "(无场景)"
    matched_terms = "、".join(result.matched_terms[:12]) if result.matched_terms else "(无)"

    return "\n".join(
        [
            f"[{index}] memory_id={memory.id}  score={result.score:.2f}  {format_local_time(memory.updated_at)}",
            f"类型：{memory.memory_type} / 置信度：{memory.confidence:.2f} / 来源：{memory.source}",
            f"场景：{scene_label}",
            f"正式记忆：{memory.memory_text}",
            f"来源消息：{memory.source_text or '(空文本)'}",
            f"命中词：{matched_terms}",
            "命中原因：" + "；".join(result.reasons),
            "",
        ]
    )


if __name__ == "__main__":
    main()
