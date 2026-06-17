"""端到端功能演示：模拟本地组件执行任务。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, "services/kaka-core/src")
sys.path.insert(0, "apps/kaka-local/src")

from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.desktop_repository import (
    complete_operation,
    get_pending_operations,
    mark_operation_executing,
)
from operations.file_ops import create_file


async def simulate_local_executor():
    """模拟本地组件执行任务。"""
    print("=" * 60)
    print("  模拟本地组件执行任务")
    print("=" * 60)

    init_database()
    session_factory = create_session_factory()

    with session_factory() as session:
        # 1. 获取待执行任务
        operations = get_pending_operations(session, limit=5)
        print(f"\n待执行任务数: {len(operations)}")

        if not operations:
            print("没有待执行任务")
            return

        # 2. 执行每个任务
        for op in operations:
            print(f"\n[任务 {op.id}] 开始执行: {op.operation_type}")
            print(f"  参数: {op.params}")

            # 标记为执行中
            mark_operation_executing(session, op.id)
            session.commit()

            try:
                # 执行操作
                if op.operation_type == "create_file":
                    result = await create_file(op.params)
                    print(f"  结果: {result['message']}")
                    print(f"  文件路径: {result.get('file_path', 'N/A')}")

                    # 完成任务
                    complete_operation(session, op.id, success=True, result=result)
                    session.commit()
                    print(f"[任务 {op.id}] 执行成功")

                else:
                    print(f"  未知操作类型: {op.operation_type}")

            except Exception as e:
                print(f"[任务 {op.id}] 执行失败: {e}")
                complete_operation(
                    session, op.id, success=False, result={"error": str(e)}
                )
                session.commit()

    print("\n" + "=" * 60)
    print("任务执行完毕")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(simulate_local_executor())
