"""QQ 适配器的 NoneBot2 启动入口。

本文件只负责启动 NoneBot2 并加载 OneBot V11 适配器和卡咔插件。
真正的消息转换、核心服务调用和响应动作转换仍然放在 qq_adapter 包里。
"""

import nonebot
from nonebot import get_bots, get_driver
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

from qq_adapter.api import create_send_api

nonebot.init(host="127.0.0.1", port=8081)

driver = get_driver()
driver.register_adapter(OneBotV11Adapter)


def _get_primary_bot():
    bots = get_bots()
    if not bots:
        raise RuntimeError("no OneBot connection is available")
    return next(iter(bots.values()))


driver.server_app.mount("/proactive", create_send_api(_get_primary_bot))

nonebot.load_plugin("qq_adapter.nonebot_plugins.kaka_chat")


if __name__ == "__main__":
    nonebot.run()
