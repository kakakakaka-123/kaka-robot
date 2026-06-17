"""端到端集成测试：完整流程验证。

测试场景：
1. QQ 消息 → kaka-core → 插件匹配 → 数据库任务创建
2. kaka-local 轮询 → 执行任务 → 上传结果
3. kaka-core 推送通知 → QQ 适配器
"""

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
for path in (
    PROJECT_ROOT / "services" / "kaka-core" / "src",
    PROJECT_ROOT / "apps" / "kaka-local" / "src",
):
    path_value = str(path)
    if path_value not in sys.path:
        sys.path.insert(0, path_value)

from kaka_core.config.settings import get_settings
from kaka_core.plugins.builtin.desktop_operations import DesktopOperationsPlugin
from kaka_core.plugins.context import PluginContext
from kaka_core.storage.database import create_session_factory, init_database
from kaka_core.storage.desktop_repository import (
    complete_operation,
    get_operation_by_id,
    get_pending_operations,
)
from kaka_protocol import MessageContent, MessageEvent, Platform, SceneType
from operations.file_ops import create_file
from operations.screenshot import take_screenshot


class TestE2EFlow:
    """端到端流程测试。"""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, tmp_path):
        """初始化数据库。"""
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'desktop-e2e.sqlite3'}")
        get_settings.cache_clear()
        init_database()
        self.session_factory = create_session_factory()
        yield
        get_settings.cache_clear()

    @pytest.mark.asyncio
    async def test_file_creation_flow(self):
        """测试文件创建完整流程。"""
        # 1. 模拟 QQ 消息
        event = MessageEvent(
            event_id="test_001",
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="test_group_123",
            user_id="test_user_456",
            display_name="测试用户",
            content=MessageContent.text_message("在桌面写个文件，内容是集成测试"),
        )

        # 2. 插件匹配
        plugin = DesktopOperationsPlugin()
        context = PluginContext.from_event(event, command_text="")

        can_handle = await plugin.can_handle(context)
        assert can_handle, "插件应该匹配该消息"

        # 3. 插件执行（创建数据库任务）
        # 注意：插件需要 session_factory，但 PluginContext 不包含它
        # 我们需要模拟插件内部行为
        from kaka_core.storage.desktop_repository import create_desktop_operation

        with self.session_factory() as session:
            operation_id = create_desktop_operation(
                session,
                operation_type="create_file",
                params={
                    "filename": "小纸条.txt",
                    "content": "集成测试",
                },
                requester_user_id=event.user_id,
                requester_scene_id=event.scene_id,
                requester_platform=event.platform.value,
                requester_scene_type=event.scene_type.value,
            )
            session.commit()

        # 4. 验证数据库任务已创建
        with self.session_factory() as session:
            operations = get_pending_operations(session, limit=10)
            assert len(operations) > 0, "应该有待执行任务"

            latest_op = get_operation_by_id(session, operation_id)
            assert latest_op is not None
            assert latest_op.operation_type == "create_file"
            assert latest_op.status == "pending"
            assert latest_op.requester_scene_type == "group"

            # 5. 模拟本地组件执行
            file_result = await create_file(latest_op.params)
            assert file_result["success"], f"文件创建失败: {file_result}"

            # 6. 更新任务状态
            complete_operation(session, latest_op.id, success=True, result=file_result)
            session.commit()

            # 7. 验证任务已完成
            completed_op = get_operation_by_id(session, latest_op.id)
            assert completed_op.status == "completed"
            assert completed_op.result["success"]

            # 8. 清理文件
            if file_result.get("file_path"):
                file_path = Path(file_result["file_path"])
                if file_path.exists():
                    file_path.unlink()

    @pytest.mark.asyncio
    async def test_screenshot_flow(self):
        """测试截图完整流程。"""
        # 1. 模拟 QQ 消息
        event = MessageEvent(
            event_id="test_002",
            platform=Platform.QQ,
            scene_type=SceneType.PRIVATE,
            scene_id="test_user_789",
            user_id="test_user_789",
            display_name="测试用户",
            content=MessageContent.text_message("截个图"),
        )

        # 2. 插件匹配
        plugin = DesktopOperationsPlugin()
        context = PluginContext.from_event(event, command_text="")

        can_handle = await plugin.can_handle(context)
        assert can_handle, "插件应该匹配该消息"

        # 3. 创建截图任务
        from kaka_core.storage.desktop_repository import create_desktop_operation

        with self.session_factory() as session:
            operation_id = create_desktop_operation(
                session,
                operation_type="screenshot",
                params={},
                requester_user_id=event.user_id,
                requester_scene_id=event.scene_id,
                requester_platform=event.platform.value,
                requester_scene_type=event.scene_type.value,
            )
            session.commit()

        # 4. 验证数据库任务
        with self.session_factory() as session:
            operations = get_pending_operations(session, limit=10)
            latest_op = get_operation_by_id(session, operation_id)
            assert latest_op is not None
            assert latest_op.operation_type == "screenshot"
            assert latest_op.status == "pending"
            assert latest_op.requester_scene_type == "private"

            # 5. 执行截图
            screenshot_result = await take_screenshot(latest_op.params)
            assert screenshot_result["success"], f"截图失败: {screenshot_result}"

            # 6. 验证截图文件存在
            screenshot_path = Path(screenshot_result["screenshot"])
            assert screenshot_path.exists(), "截图文件应该存在"
            assert screenshot_path.stat().st_size > 0, "截图文件不应为空"

            # 7. 更新任务状态
            complete_operation(session, latest_op.id, success=True, result=screenshot_result)
            session.commit()

            # 8. 验证任务已完成
            completed_op = get_operation_by_id(session, latest_op.id)
            assert completed_op.status == "completed"
            assert completed_op.result["success"]

            # 清理截图文件（保留最近 3 个）
            screenshots_dir = screenshot_path.parent
            screenshots = sorted(screenshots_dir.glob("*.png"))
            if len(screenshots) > 3:
                for old_screenshot in screenshots[:-3]:
                    old_screenshot.unlink()

    @pytest.mark.asyncio
    async def test_plugin_not_matching(self):
        """测试插件不匹配的情况。"""
        # 普通聊天消息
        event = MessageEvent(
            event_id="test_003",
            platform=Platform.QQ,
            scene_type=SceneType.GROUP,
            scene_id="test_group_123",
            user_id="test_user_456",
            display_name="测试用户",
            content=MessageContent.text_message("你好啊"),
        )

        plugin = DesktopOperationsPlugin()
        context = PluginContext.from_event(event, command_text="")

        can_handle = await plugin.can_handle(context)
        assert not can_handle, "插件不应该匹配普通聊天消息"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
