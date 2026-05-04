"""QQ 适配器的 NoneBot2 启动入口。

本文件只负责启动 NoneBot2 并加载 OneBot V11 适配器和卡咔插件。
真正的消息转换、核心服务调用和响应动作转换仍然放在 qq_adapter 包里。
"""

import nonebot
from nonebot import get_driver
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

nonebot.init(host="127.0.0.1", port=8081)

driver = get_driver()
driver.register_adapter(OneBotV11Adapter)

nonebot.load_plugin("qq_adapter.nonebot_plugins.kaka_chat")


if __name__ == "__main__":
    nonebot.run()
