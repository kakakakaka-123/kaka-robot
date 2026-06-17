"""卡咔本地组件主程序。"""

import asyncio
import sys
from pathlib import Path

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from executor import KakaLocalExecutor


async def main():
    """主函数。"""
    config = load_config()
    executor = KakaLocalExecutor(config)

    print("=" * 50)
    print("  卡咔本地组件")
    print("=" * 50)

    await executor.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n已退出")
