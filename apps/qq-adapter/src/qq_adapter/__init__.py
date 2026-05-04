"""卡咔 的 QQ 适配器。

当前阶段先实现可测试的适配逻辑：
- 把 QQ 原始事件转换成统一 MessageEvent。
- 调用 kaka-core 的 HTTP API。
- 把 KakaResponse 转换成 QQ 侧待发送动作。

真正的 NoneBot 接入会在下一步接上。
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
