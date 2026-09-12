"""Web API 路由聚合。"""

from fastapi import APIRouter

from . import agents, runs, sessions, settings


api_router = APIRouter(prefix="/api")
api_router.include_router(agents.router)
api_router.include_router(sessions.router)
api_router.include_router(runs.router)
api_router.include_router(settings.router)


@api_router.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """返回进程和数据库生命周期已经就绪的轻量状态。"""
    return {"version": "0.1.0", "database": "ready"}
