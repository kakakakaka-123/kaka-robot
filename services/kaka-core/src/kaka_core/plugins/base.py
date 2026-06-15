from typing import Protocol

from kaka_core.plugins.context import PluginContext
from kaka_core.plugins.result import PluginResult


class KakaPlugin(Protocol):
    """卡咔插件协议。"""

    id: str
    name: str
    description: str

    async def can_handle(self, context: PluginContext) -> bool:
        """判断插件是否能处理当前上下文。"""

    async def run(self, context: PluginContext) -> PluginResult:
        """执行插件并返回抽象结果。"""
