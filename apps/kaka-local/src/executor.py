"""卡咔本地执行组件核心。"""

import asyncio
import sys
from pathlib import Path

import httpx

# 添加当前目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from config import Config
from operations.file_ops import create_file
from operations.screenshot import take_screenshot
from operations.sound import play_sound


class KakaLocalExecutor:
    """卡咔的本地执行组件。

    轮询 kaka-core 获取任务，执行后上传结果。
    """

    def __init__(self, config: Config):
        self.core_url = config.core_url
        self.poll_interval = config.poll_interval
        self.client = httpx.AsyncClient(timeout=30)

    async def run(self):
        """主循环：轮询并执行任务。"""
        print(f"卡咔本地组件已启动，连接到 {self.core_url}")
        print(f"轮询间隔: {self.poll_interval} 秒")

        while True:
            try:
                # 1. 获取待执行任务
                operations = await self.fetch_pending_operations()

                # 2. 逐个执行
                for op in operations:
                    await self.execute_operation(op)

                # 3. 等待下次轮询
                await asyncio.sleep(self.poll_interval)

            except KeyboardInterrupt:
                print("\n正在退出...")
                break
            except Exception as e:
                print(f"错误：{e}")
                await asyncio.sleep(10)

        await self.client.aclose()

    async def fetch_pending_operations(self) -> list[dict]:
        """从 kaka-core 获取待执行任务。"""
        try:
            response = await self.client.get(f"{self.core_url}/v1/desktop/operations/pending")
            response.raise_for_status()
            data = response.json()
            return data.get("operations", [])
        except httpx.HTTPError as e:
            print(f"获取任务失败：{e}")
            return []

    async def execute_operation(self, operation: dict):
        """执行具体操作。"""
        op_id = operation["id"]
        op_type = operation["operation_type"]
        params = operation["params"]

        print(f"\n[任务 {op_id}] 开始执行：{op_type}")

        # 标记为执行中
        await self.mark_executing(op_id)

        try:
            # 根据类型分发
            if op_type == "create_file":
                result = await create_file(params)
            elif op_type == "screenshot":
                result = await take_screenshot(params)
            elif op_type == "play_sound":
                result = await play_sound(params)
            else:
                raise ValueError(f"未知操作类型：{op_type}")

            success = bool(result.get("success", True))
            await self.report_result(op_id, success=success, result=result)
            if success:
                print(f"[任务 {op_id}] 执行成功：{result.get('message', '')}")
            else:
                print(f"[任务 {op_id}] 执行失败：{result.get('message', result.get('error', '未知错误'))}")

        except Exception as e:
            # 上传失败结果
            error_msg = str(e)
            await self.report_result(
                op_id, success=False, result={"error": error_msg, "message": f"执行失败：{error_msg}"}
            )
            print(f"[任务 {op_id}] 执行失败：{error_msg}")

    async def mark_executing(self, operation_id: int):
        """标记操作开始执行。"""
        try:
            await self.client.post(f"{self.core_url}/v1/desktop/operations/{operation_id}/start")
        except httpx.HTTPError as e:
            print(f"标记执行状态失败：{e}")

    async def report_result(self, operation_id: int, success: bool, result: dict):
        """上传执行结果。"""
        try:
            await self.client.post(
                f"{self.core_url}/v1/desktop/operations/{operation_id}/complete",
                json={"success": success, "result": result},
            )
        except httpx.HTTPError as e:
            print(f"上传结果失败：{e}")
