"""端到端测试：截图功能完整流程。"""

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for path in (
    PROJECT_ROOT / "services" / "kaka-core" / "src",
    PROJECT_ROOT / "apps" / "kaka-local" / "src",
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.desktop_repository import create_desktop_operation, get_pending_operations
from operations.screenshot import take_screenshot
from kaka_core.config.settings import get_settings


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'script-screenshot-e2e.sqlite3'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_screenshot_e2e():
    """测试截图功能端到端流程。"""
    print("=" * 60)
    print("  截图功能端到端测试")
    print("=" * 60)

    init_database()
    session_factory = create_session_factory()

    # 1. 创建截图任务
    print("\n[Step 1] 创建截图任务...")
    with session_factory() as session:
        operation_id = create_desktop_operation(
            session,
            operation_type="screenshot",
            params={"blur_sensitive": False, "quality": 85},
            requester_user_id="test_user",
            requester_scene_id="test_group_123",
            requester_platform="qq",
            requester_scene_type="group",
        )
        session.commit()
        print(f"OK: 任务已创建，ID: {operation_id}")

    # 2. 模拟本地组件执行
    print("\n[Step 2] 执行截图任务...")
    result = await take_screenshot({"blur_sensitive": False, "quality": 85})

    if result["success"]:
        print(f"OK: {result['message']}")
        print(f"  截图路径: {result['screenshot']}")
        print(f"  分辨率: {result['width']}x{result['height']}")

        # 检查文件
        screenshot_path = Path(result["screenshot"])
        if screenshot_path.exists():
            print(f"  文件大小: {screenshot_path.stat().st_size / 1024:.1f} KB")
        else:
            print("  WARN: 文件不存在")
    else:
        print(f"FAIL: {result['message']}")

    print("\n" + "=" * 60)
    print("端到端测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_screenshot_e2e())
