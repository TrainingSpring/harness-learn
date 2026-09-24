"""Harness Web API 的 FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .bootstrap import install_agent_source_path

# API 模块会直接导入当前尚未独立打包的 runtime/storage，因此 bootstrap
# 必须发生在路由导入之前，不能依赖 pytest 或调用方预先修改 sys.path。
install_agent_source_path()

from .api.router import api_router
from .config import WebServerSettings
from .dependencies import ApplicationServices
from .errors import install_error_handlers
from .services.agent_profile_assistant import AgentProfileAssistant
from .services.chat_service import ChatService
from .services.run_registry import RunRegistry
from .static import SpaStaticFiles

from session.session_service import SessionService
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from storage.repositories.context_item import ContextItemRepository
from storage.repositories.session_query import SessionQueryRepository
from tools.registry.catalog import ToolCatalog


def create_app(settings: WebServerSettings) -> FastAPI:
    """创建绑定指定 workspace 的 FastAPI 应用。

    Args:
        settings: 已校验的本地服务启动参数。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """初始化一次共享数据库与核心服务，并在退出时释放连接。"""
        database = StateDatabase(str(settings.workspace))
        database.initialize()
        catalog = ToolCatalog()
        session_queries = SessionQueryRepository(database)
        context_items = ContextItemRepository(database)
        llm_profiles = LLMProfileRepository(database)
        run_registry = RunRegistry()
        session_service = SessionService(database)
        app.state.services = ApplicationServices(
            database=database,
            session_service=session_service,
            agent_profiles=AgentProfileRepository(database),
            llm_profiles=llm_profiles,
            agent_profile_assistant=AgentProfileAssistant(llm_profiles),
            tool_catalog=catalog,
            session_queries=session_queries,
            context_items=context_items,
            run_registry=run_registry,
            chat_service=ChatService(
                session_service,
                session_queries,
                context_items,
                run_registry,
            ),
        )
        try:
            yield
        finally:
            run_registry.clear()
            database.close()

    app = FastAPI(
        title="Harness Web API",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.include_router(api_router)
    if settings.frontend_dist is not None:
        # 必须最后挂载根路径，否则会截获前面定义的 /api 路由。
        app.mount("/", SpaStaticFiles(settings.frontend_dist), name="frontend")
    return app


def default_app() -> FastAPI:
    """为 ``uvicorn app.main:app`` 创建以当前目录为 workspace 的应用。"""
    return create_app(WebServerSettings(workspace=Path.cwd()))


app = default_app()
