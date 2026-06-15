"""卡咔核心服务本地开发启动入口。

这个文件主要给 PyCharm 使用。直接运行它，就等价于执行：

    python -m uvicorn kaka_core.api.app:app --reload --port 8001

正式部署时仍然建议使用 uvicorn 命令或 Docker 配置启动。
"""

from pathlib import Path

import uvicorn

if __name__ == "__main__":
    # 开启热重载适合本地开发：只监听核心源码，避免修改脚本、测试或文档时重启后台任务。
    service_root = Path(__file__).resolve().parent
    uvicorn.run(
        "kaka_core.api.app:app",
        host="127.0.0.1",
        port=8001,
        reload=True,
        reload_dirs=[str(service_root / "src")],
    )
