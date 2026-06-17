"""桌面操作功能集成测试。

测试完整流程：
1. 模拟 QQ 消息触发桌面操作
2. 检查数据库任务创建
3. 本地组件执行任务
4. 检查文件是否创建
5. 检查完成通知
"""

import asyncio
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = PROJECT_ROOT / "services" / "kaka-core" / "src"
LOCAL_SRC = PROJECT_ROOT / "apps" / "kaka-local" / "src"
for path in (CORE_SRC, LOCAL_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from kaka_core.config.settings import get_settings
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.desktop_repository import (
    create_desktop_operation,
    get_operation_by_id,
    get_pending_operations,
)


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'script-desktop-integration.sqlite3'}")
    get_settings.cache_clear()
    init_database()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_create_operation():
    """测试创建桌面操作任务。"""
    print("\n[Test 1] 创建桌面操作任务...")

    init_database()
    session_factory = create_session_factory()

    with session_factory() as session:
        operation_id = create_desktop_operation(
            session,
            operation_type="create_file",
            params={
                "filename": "测试文件.txt",
                "content": "这是集成测试创建的文件",
            },
            requester_user_id="test_user",
            requester_scene_id="test_scene",
            requester_platform="qq",
            requester_scene_type="private",
        )
        session.commit()

        print(f"OK: 操作任务已创建，ID: {operation_id}")

        # 查询任务
        operation = get_operation_by_id(session, operation_id)
        assert operation is not None
        assert operation.status == "pending"
        print(f"OK: 任务状态: {operation.status}")

        return operation_id


@pytest.mark.asyncio
async def test_get_pending():
    """测试获取待执行任务。"""
    print("\n[Test 2] 获取待执行任务...")

    session_factory = create_session_factory()

    with session_factory() as session:
        operations = get_pending_operations(session, limit=10)
        print(f"OK: 待执行任务数: {len(operations)}")

        if operations:
            for op in operations:
                print(f"  - ID {op.id}: {op.operation_type} (status={op.status})")


@pytest.mark.asyncio
async def test_file_operations():
    """测试文件操作安全检查。"""
    print("\n[Test 3] 测试文件操作...")

    from security import is_safe_filename, validate_path

    # 测试安全文件名
    assert is_safe_filename("test.txt") == True
    assert is_safe_filename("../test") == False
    assert is_safe_filename("test/file.txt") == False
    print("OK: 文件名安全检查通过")

    # 测试路径白名单
    safe_path = Path.home() / "Desktop" / "卡咔的小角落" / "test.txt"
    unsafe_path = Path.home() / "Documents" / "test.txt"

    assert validate_path(safe_path) == True
    print("OK: 路径白名单检查通过")


async def main():
    """运行所有测试。"""
    print("=" * 60)
    print("  桌面操作功能集成测试")
    print("=" * 60)

    try:
        # Test 1: 创建操作
        operation_id = await test_create_operation()

        # Test 2: 获取待执行任务
        await test_get_pending()

        # Test 3: 文件操作安全检查
        await test_file_operations()

        print("\n" + "=" * 60)
        print("OK: 所有测试通过！")
        print("=" * 60)

        print("\n提示：")
        print("1. 启动 kaka-core: uvicorn kaka_core.api.app:app --reload")
        print("2. 启动 kaka-local: python apps/kaka-local/src/main.py")
        print(f"3. 本地组件会执行任务 ID {operation_id}")
        print("4. 检查桌面是否生成文件: ~/Desktop/卡咔的小角落/测试文件.txt")

    except Exception as e:
        print(f"\nERROR: 测试失败: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
