"""卡咔的桌面操作能力插件。

卡咔可以在主人电脑上执行操作（创建文件、截图等）。
对外不暴露"助手"概念，能力归属卡咔本身。
"""

import random
import re

from kaka_core.config.settings import get_settings
from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.result import PluginResult
from kaka_core.storage.database import create_session_factory
from kaka_core.storage.desktop_repository import create_desktop_operation
from kaka_protocol import MessageEvent


class DesktopOperationsPlugin:
    """卡咔的桌面操作能力。"""

    id = "desktop_operations"
    name = "桌面操作"
    description = "卡咔的桌面操作能力（创建文件、截图等）"

    async def can_handle(self, context: PluginContext) -> bool:
        """判断是否可以处理该消息。"""
        # 不处理命令模式（/xxx 或 插件：xxx）
        if context.command_text:
            return False

        # 匹配桌面操作关键词
        text = context.text.lower()
        keywords = [
            "在桌面",
            "创建文件",
            "写个文件",
            "写文件",
            "桌面写",
            "截图",
            "截个图",
        ]

        return any(keyword in text for keyword in keywords)

    async def run(self, context: PluginContext) -> PluginResult:
        """执行桌面操作。"""
        # 1. 解析指令
        command = self._parse_command(context.text)

        if not command:
            return PluginResult.no_reply(self.id)

        # 2. 权限检查（暂时简化：只检查是否是创造者）
        settings = get_settings()
        is_owner = context.user_id in settings.relationship.owner_user_ids

        # 非创造者的高权限操作拒绝
        if command.get("permission_level", 1) >= 2 and not is_owner:
            return PluginResult.text_reply(self.id, "这个操作我不能做哦...")

        # 3. 创建操作任务
        operation_id = self._create_operation(context, command)

        # 4. 立即回复（体现"我正在做"）
        reply_text = self._get_initial_response(command["operation_type"])

        return PluginResult.text_reply(
            self.id,
            reply_text,
            metadata={
                "operation_id": operation_id,
                "operation_type": command["operation_type"],
            },
        )

    def _parse_command(self, text: str) -> dict | None:
        """解析用户指令。

        示例：
        - "在桌面写个文件，内容是今天要早睡" -> create_file
        - "截个图" -> screenshot
        """
        text_lower = text.lower()

        # 创建文件
        if any(kw in text_lower for kw in ["创建文件", "写文件", "写个文件", "在桌面写", "桌面写"]):
            # 尝试提取内容
            content = self._extract_file_content(text)
            filename = self._extract_filename(text)

            return {
                "operation_type": "create_file",
                "params": {
                    "filename": filename,
                    "content": content,
                },
                "permission_level": 1,
            }

        # 截图
        if any(kw in text_lower for kw in ["截图", "截个图"]):
            return {
                "operation_type": "screenshot",
                "params": {},
                "permission_level": 1,
            }

        return None

    def _extract_file_content(self, text: str) -> str:
        """从文本中提取要写入文件的内容。"""
        # 匹配 "内容是XXX" "写XXX" 等模式
        patterns = [
            r"内容是[：:](.*)",
            r"内容[：:](.*)",
            r"写[：:](.*)",
            r"提醒[：:]?(.*)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                content = match.group(1).strip()
                # 去除引号
                content = content.strip('"\'""''')
                if content:
                    return content

        # 如果没有明确内容，返回整个消息（去掉指令部分）
        for kw in ["创建文件", "写文件", "写个文件", "在桌面写", "桌面写"]:
            if kw in text:
                parts = text.split(kw, 1)
                if len(parts) > 1:
                    content = parts[1].strip("，,。. \t")
                    if content:
                        return content

        return "（来自卡咔的小纸条）"

    def _extract_filename(self, text: str) -> str:
        """从文本中提取文件名。"""
        # 匹配 "文件名是XXX" 等模式
        patterns = [
            r"文件名[是为][：:]?(.*?)(?:[，,。.\s]|$)",
            r"叫[：:]?(.*?)(?:[，,。.\s]|$)",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                filename = match.group(1).strip()
                filename = filename.strip('"\'""''')
                if filename and not filename.endswith(".txt"):
                    filename += ".txt"
                if filename:
                    return filename

        # 默认文件名
        return "小纸条.txt"

    def _get_initial_response(self, operation_type: str) -> str:
        """获取操作开始时的回复（强调"我来做"）。"""
        responses = {
            "create_file": ["好的，我来写~", "嗯嗯，马上~", "收到~", "我写给你看~"],
            "screenshot": ["我截个图~", "稍等，我拍一下~", "好~", "让我看看~"],
            "play_sound": ["好的，我放给你听~", "马上~"],
        }

        return random.choice(responses.get(operation_type, ["好的~"]))

    def _create_operation(self, context: PluginContext, command: dict) -> int:
        """创建操作任务。"""
        session_factory = create_session_factory()

        with session_factory() as session:
            operation_id = create_desktop_operation(
                session,
                operation_type=command["operation_type"],
                params=command.get("params", {}),
                requester_user_id=context.user_id,
                requester_scene_id=context.scene_id,
                requester_platform=context.platform,
                requester_scene_type=context.scene_type,
                approved=True,
                permission_level=command.get("permission_level", 1),
            )
            session.commit()

        return operation_id
