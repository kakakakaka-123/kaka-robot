"""测试截图功能。"""

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOCAL_SRC = PROJECT_ROOT / "apps" / "kaka-local" / "src"
if str(LOCAL_SRC) not in sys.path:
    sys.path.insert(0, str(LOCAL_SRC))

from operations.screenshot import take_screenshot


@pytest.mark.asyncio
async def test_screenshot():
    """测试截图功能。"""
    print("=" * 60)
    print("  测试截图功能")
    print("=" * 60)

    # 测试 1：基本截图
    print("\n[Test 1] 基本截图...")
    result = await take_screenshot({})

    if result["success"]:
        print(f"OK: {result['message']}")
        print(f"  文件路径: {result['screenshot']}")
        print(f"  分辨率: {result['width']}x{result['height']}")

        # 检查文件是否存在
        screenshot_path = Path(result["screenshot"])
        if screenshot_path.exists():
            print(f"  文件大小: {screenshot_path.stat().st_size / 1024:.1f} KB")
            print("OK: 文件已创建")
        else:
            print("FAIL: 文件不存在")
    else:
        print(f"FAIL: {result['message']}")

    # 测试 2：模糊敏感信息
    print("\n[Test 2] 模糊敏感信息...")
    result = await take_screenshot({"blur_sensitive": True})

    if result["success"]:
        print(f"OK: {result['message']}")
        print(f"  文件路径: {result['screenshot']}")
    else:
        print(f"FAIL: {result['message']}")

    # 测试 3：指定质量
    print("\n[Test 3] 低质量截图（压缩）...")
    result = await take_screenshot({"quality": 50})

    if result["success"]:
        print(f"OK: {result['message']}")
        screenshot_path = Path(result["screenshot"])
        print(f"  文件大小: {screenshot_path.stat().st_size / 1024:.1f} KB")
    else:
        print(f"FAIL: {result['message']}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    # 显示截图目录
    screenshots_dir = Path.home() / ".kaka" / "screenshots"
    print(f"\n截图保存位置: {screenshots_dir}")
    print(f"文件列表:")
    for file in sorted(screenshots_dir.glob("*.png"))[-5:]:
        size_kb = file.stat().st_size / 1024
        print(f"  - {file.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    asyncio.run(test_screenshot())
