"""Harness Web API 的 FastAPI 应用入口。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from .api.router import api_router
from .bootstrap import install_agent_source_path
from .config import WebServerSettings
from .dependencies import ApplicationServices
from .errors import install_error_handlers

install_agent_source_path()

from runtime.agent_directory import AgentDirectory
from runtime.agent_factory import AgentFactory
from runtime.session_service import SessionService
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from storage.repositories.context_item import ContextItemRepository
from storage.repositories.session_query import SessionQueryRepository
from tools.catalog import ToolCatalog


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
        app.state.services = ApplicationServices(
            database=database,
            agent_directory=AgentDirectory(AgentProfileRepository(database)),
            agent_factory=AgentFactory(database, tool_catalog=catalog),
            session_service=SessionService(database),
            llm_profiles=LLMProfileRepository(database),
            tool_catalog=catalog,
            session_queries=SessionQueryRepository(database),
            context_items=ContextItemRepository(database),
        )
        try:
            yield
        finally:
            database.close()

    app = FastAPI(
        title="Harness Web API",
        version="0.1.0",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.include_router(api_router)
    return app


def default_app() -> FastAPI:
    """为 ``uvicorn app.main:app`` 创建以当前目录为 workspace 的应用。"""
    return create_app(WebServerSettings(workspace=Path.cwd()))


app = default_app()
