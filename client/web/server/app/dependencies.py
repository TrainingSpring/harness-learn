"""FastAPI 路由共享的应用服务依赖。"""

from dataclasses import dataclass

from fastapi import Request

from .bootstrap import install_agent_source_path

install_agent_source_path()

from session.session_service import SessionService
from storage.database import StateDatabase
from storage.repositories.agent_profile import AgentProfileRepository
from storage.repositories.llm_profile import LLMProfileRepository
from storage.repositories.context_item import ContextItemRepository
from storage.repositories.session_query import SessionQueryRepository
from tools.registry.catalog import ToolCatalog

from .services.chat_service import ChatService
from .services.agent_profile_assistant import AgentProfileAssistant
from .services.run_registry import RunRegistry


@dataclass
class ApplicationServices:
    """保存一个应用生命周期内复用的核心服务。

    Attributes:
        database: workspace 唯一的 SQLite 连接管理器。
        session_service: 遵守固定成员约束的会话创建服务。
        agent_profiles: AgentProfile 写入和读取仓储。
        llm_profiles: LLM 配置只读接口使用的仓储。
        agent_profile_assistant: 使用指定 LLM 生成角色草案的服务。
        tool_catalog: 受信任工具元数据目录。
        session_queries: 面向客户端的 DIRECT 会话聚合查询仓储。
        context_items: 会话时间线查询仓储。
        run_registry: 进程内活动 SessionExecution 注册表。
        chat_service: SessionExecution 到 SSE 的应用服务。
    """

    database: StateDatabase
    session_service: SessionService
    agent_profiles: AgentProfileRepository
    llm_profiles: LLMProfileRepository
    agent_profile_assistant: AgentProfileAssistant
    tool_catalog: ToolCatalog
    session_queries: SessionQueryRepository
    context_items: ContextItemRepository
    run_registry: RunRegistry
    chat_service: ChatService


async def get_services(request: Request) -> ApplicationServices:
    """从当前 FastAPI 应用读取共享服务容器。

    Args:
        request: 当前 HTTP 请求，提供应用生命周期状态。
    """
    return request.app.state.services


async def get_database(request: Request) -> StateDatabase:
    """返回应用生命周期内唯一的状态数据库。"""
    return request.app.state.services.database


async def get_session_service(request: Request) -> SessionService:
    """返回固定成员会话服务。"""
    return request.app.state.services.session_service
