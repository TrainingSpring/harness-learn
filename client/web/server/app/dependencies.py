"""FastAPI 路由共享的应用服务依赖。"""

from dataclasses import dataclass

from fastapi import Request

from .bootstrap import install_agent_source_path

install_agent_source_path()

from runtime.agent_directory import AgentDirectory
from runtime.agent_factory import AgentFactory
from runtime.session_service import SessionService
from storage.database import StateDatabase
from storage.repositories.llm_profile import LLMProfileRepository
from tools.catalog import ToolCatalog


@dataclass
class ApplicationServices:
    """保存一个应用生命周期内复用的核心服务。

    Attributes:
        database: workspace 唯一的 SQLite 连接管理器。
        agent_directory: 可供 UI 查询的 Agent 目录。
        agent_factory: 从持久化配置创建运行时 Agent 的工厂。
        session_service: 遵守固定成员约束的会话创建服务。
        llm_profiles: LLM 配置只读接口使用的仓储。
        tool_catalog: 受信任工具元数据目录。
    """

    database: StateDatabase
    agent_directory: AgentDirectory
    agent_factory: AgentFactory
    session_service: SessionService
    llm_profiles: LLMProfileRepository
    tool_catalog: ToolCatalog


async def get_services(request: Request) -> ApplicationServices:
    """从当前 FastAPI 应用读取共享服务容器。

    Args:
        request: 当前 HTTP 请求，提供应用生命周期状态。
    """
    return request.app.state.services


async def get_database(request: Request) -> StateDatabase:
    """返回应用生命周期内唯一的状态数据库。"""
    return request.app.state.services.database


async def get_agent_directory(request: Request) -> AgentDirectory:
    """返回角色发现服务。"""
    return request.app.state.services.agent_directory


async def get_agent_factory(request: Request) -> AgentFactory:
    """返回运行时 Agent 工厂。"""
    return request.app.state.services.agent_factory


async def get_session_service(request: Request) -> SessionService:
    """返回固定成员会话服务。"""
    return request.app.state.services.session_service
