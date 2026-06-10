from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PluginResult:
    """插件执行结果。

    插件只返回抽象结果，不直接调用 QQ、微信或桌宠 API。
    """

    plugin_id: str
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    should_reply: bool = True

    @classmethod
    def text_reply(
        cls,
        plugin_id: str,
        text: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "PluginResult":
        return cls(plugin_id=plugin_id, text=text, metadata=metadata or {})
