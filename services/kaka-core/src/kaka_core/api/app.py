from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from kaka_core.api.admin_routes import admin_api_router, mount_web_console
from kaka_core.api.routes import router
from kaka_core.memory.auto_analysis import create_auto_analysis_scheduler
from kaka_core.memory.auto_review import create_auto_review_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    analysis_scheduler = create_auto_analysis_scheduler()
    review_scheduler = create_auto_review_scheduler()
    app.state.memory_auto_analysis_scheduler = analysis_scheduler
    app.state.memory_auto_review_scheduler = review_scheduler
    analysis_scheduler.start()
    review_scheduler.start()
    try:
        yield
    finally:
        await review_scheduler.stop()
        await analysis_scheduler.stop()


def create_app() -> FastAPI:
    """创建接口服务应用实例。

    使用工厂函数可以让测试、开发服务器和未来部署复用同一套应用创建逻辑。
    """

    app = FastAPI(
        title="Kaka Core",
        description="卡咔 v2 的核心大脑 API。",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(admin_api_router)
    mount_web_console(app)
    return app


app = create_app()
