"""灌入一批长期记忆 E2E 测试数据。

这是临时测试脚本，只用于构造可控的输入样本，方便跑完整条记忆链路。
默认只预览，不写库；确认后加 --apply。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "kaka-core" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from kaka_core.storage.database import create_session_factory, init_database  # noqa: E402
from kaka_core.storage.models import InputRecord, SceneRecord, UserRecord  # noqa: E402

LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")
BASE_TIME = datetime(2026, 5, 2, 4, 0, tzinfo=timezone.utc)

# PyCharm 简单模式：默认只预览，不写库。
# 只有同时把 PYCHARM_APPLY 和 PYCHARM_CONFIRM_SEED 改成 True，右键运行才会写入测试输入。
PYCHARM_LIMIT_PREVIEW = 20
PYCHARM_APPLY = False
PYCHARM_CONFIRM_SEED = False

# 高级模式：非空时覆盖上面的简单模式；外部真实命令行参数优先级最高。
PYCHARM_DEFAULT_ARGS: list[str] = []


@dataclass(frozen=True)
class SeedItem:
    key: str
    scene_key: str
    minutes_offset: int
    text: str


USERS = {
    "u1": {
        "platform_user_id": "990000001",
        "display_name": "测试用户A",
    },
    "u2": {
        "platform_user_id": "990000002",
        "display_name": "测试用户B",
    },
}

SCENES = {
    "group": {
        "scene_type": "group",
        "scene_id": "990001",
    },
    "private_u1": {
        "scene_type": "private",
        "scene_id": USERS["u1"]["platform_user_id"],
    },
}

GROUP_ITEMS = [
    SeedItem("u1", "group", 0, "我是物联网工程专业的大三学生，名字叫阿澈。"),
    SeedItem("u2", "group", 2, "我是做前端的，主要用 Vue 和 TypeScript。"),
    SeedItem("u1", "group", 4, "我喜欢先给结论，再给理由。"),
    SeedItem("u2", "group", 6, "我不喜欢太花哨的界面。"),
    SeedItem("u1", "group", 8, "以后回答时请尽量用第三人称，不要总说我。"),
    SeedItem("u2", "group", 10, "以后群里别 @ 我太多次。"),
    SeedItem("u1", "group", 12, "我最近在做卡咔 v2 的长期记忆测试。"),
    SeedItem("u2", "group", 14, "我最近在学 Python。"),
    SeedItem("u1", "group", 16, "这个项目里正式记忆和候选区要分开。"),
    SeedItem("u2", "group", 18, "他是我导师王老师。"),
    SeedItem("u1", "group", 20, "我准备把记忆模型切到 deepseek-v4-flash。"),
    SeedItem("u2", "group", 22, "我们团队今天定了规则：先写候选，再合并。"),
    SeedItem("u1", "group", 24, "他是我室友小陈，负责前端。"),
    SeedItem("u2", "group", 26, "这个先记一下。"),
    SeedItem("u1", "group", 28, "我明天要去面试，后天再看结果。"),
    SeedItem("u2", "group", 30, "哈哈，这个不错。"),
    SeedItem("u1", "group", 32, "记住我不喜欢太长的回答。"),
    SeedItem("u2", "group", 34, "先这样吧。"),
    SeedItem("u1", "group", 36, "我们先把 prompt 分成分类、复核、检索三层。"),
    SeedItem("u2", "group", 38, "嗯嗯"),
    SeedItem("u1", "group", 40, "这个先别记。"),
    SeedItem("u2", "group", 42, "我希望回复别太长。"),
    SeedItem("u1", "group", 44, "就按这个来。"),
    SeedItem("u2", "group", 46, "明天要交作业。"),
    SeedItem("u1", "group", 48, "这个流程先保持住。"),
    SeedItem("u2", "group", 50, "我平时更喜欢你直接给结论。"),
    SeedItem("u1", "group", 52, "回复时先给结论。"),
    SeedItem("u2", "group", 54, "我现在先测这一版。"),
    SeedItem("u1", "group", 56, "我更希望你别过度展开。"),
    SeedItem("u2", "group", 58, "那行。"),
]

PRIVATE_ITEMS = [
    SeedItem("u1", "private_u1", 0, "我平时更希望你直接给结论。"),
    SeedItem("u1", "private_u1", 2, "我明天上午要去医院体检。"),
    SeedItem("u1", "private_u1", 4, "这个数量先固定成 5 条。"),
    SeedItem("u1", "private_u1", 6, "就先这样。"),
    SeedItem("u1", "private_u1", 8, "记住我之后要先看候选区再合并。"),
    SeedItem("u1", "private_u1", 10, "我会把提示词分三层。"),
    SeedItem("u1", "private_u1", 12, "先别把它接入聊天回复。"),
    SeedItem("u1", "private_u1", 14, "以后记得区分候选和正式记忆。"),
    SeedItem("u1", "private_u1", 16, "谢谢"),
    SeedItem("u1", "private_u1", 18, "好的"),
]


def main() -> None:
    args = parse_args()

    init_database()
    session_factory = create_session_factory()
    with session_factory() as session:
        preview, inserted = seed(session, apply=args.apply)
        if args.apply:
            session.commit()

    print("E2E 测试数据种子预览" if not args.apply else "E2E 测试数据种子写入完成")
    print("=" * 60)
    print(f"本次计划/写入：{len(preview)} 条")
    print(f"实际新增：{inserted} 条")
    print("样本分布：")
    print(f"  group: {len(GROUP_ITEMS)}")
    print(f"  private: {len(PRIVATE_ITEMS)}")
    print("=" * 60)
    for line in preview[: max(0, args.limit_preview)]:
        print(line)


def parse_args() -> argparse.Namespace:
    if len(sys.argv) > 1:
        return parse_args_from_list(None)
    if PYCHARM_DEFAULT_ARGS:
        return parse_args_from_list(PYCHARM_DEFAULT_ARGS)
    return parse_args_from_list(build_pycharm_simple_args())


def build_pycharm_simple_args() -> list[str]:
    args = ["--limit-preview", str(PYCHARM_LIMIT_PREVIEW)]
    if PYCHARM_APPLY:
        if not PYCHARM_CONFIRM_SEED:
            raise SystemExit(
                "PYCHARM_APPLY=True 会写入测试输入；确认后还需要把 PYCHARM_CONFIRM_SEED 改成 True。"
            )
        args.append("--apply")
    return args


def parse_args_from_list(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="灌入记忆 E2E 测试数据。")
    parser.add_argument("--apply", action="store_true", help="真正写入数据库。")
    parser.add_argument("--limit-preview", type=int, default=20, help="最多展示多少条预览。")
    return parser.parse_args(argv)


def seed(session, *, apply: bool) -> tuple[list[str], int]:
    preview: list[str] = []
    inserted = 0

    users = {key: get_or_create_user(session, key) for key in USERS}
    scenes = {
        "group": get_or_create_scene(session, SCENES["group"]),
        "private_u1": get_or_create_scene(session, SCENES["private_u1"]),
    }

    for item in GROUP_ITEMS + PRIVATE_ITEMS:
        user = users[item.key]
        scene = scenes[item.scene_key]
        event_id = build_event_id(item)
        existing = session.scalar(select(InputRecord).where(InputRecord.event_id == event_id))
        local_time = format_local_time(BASE_TIME + timedelta(minutes=item.minutes_offset))
        preview.append(f"{event_id} | {local_time} | {item.text}")
        if existing is not None or not apply:
            continue
        session.add(
            InputRecord(
                event_id=event_id,
                user_id=user.id,
                scene_id=scene.id,
                content_type="text",
                content_text=item.text,
                raw_event={"seed": "memory-e2e"},
                extra_metadata={"seed": "memory-e2e"},
                analysis_status="not_analyzed",
                created_at=BASE_TIME + timedelta(minutes=item.minutes_offset),
            )
        )
        inserted += 1

    if apply:
        session.flush()
    return preview, inserted


def build_event_id(item: SeedItem) -> str:
    scene_code = "g" if item.scene_key == "group" else "p"
    user_code = item.key
    return f"e2e-20260502-{scene_code}-{user_code}-{item.minutes_offset:02d}"


def get_or_create_user(session, key: str) -> UserRecord:
    spec = USERS[key]
    user = session.scalar(
        select(UserRecord).where(
            UserRecord.platform == "qq",
            UserRecord.platform_user_id == spec["platform_user_id"],
        )
    )
    if user is not None:
        return user
    user = UserRecord(
        platform="qq",
        platform_user_id=spec["platform_user_id"],
        display_name=spec["display_name"],
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(user)
    session.flush()
    return user


def get_or_create_scene(session, spec: dict[str, str]) -> SceneRecord:
    scene = session.scalar(
        select(SceneRecord).where(
            SceneRecord.platform == "qq",
            SceneRecord.scene_type == spec["scene_type"],
            SceneRecord.scene_id == spec["scene_id"],
        )
    )
    if scene is not None:
        return scene
    scene = SceneRecord(
        platform="qq",
        scene_type=spec["scene_type"],
        scene_id=spec["scene_id"],
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    session.add(scene)
    session.flush()
    return scene


def format_local_time(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    main()
