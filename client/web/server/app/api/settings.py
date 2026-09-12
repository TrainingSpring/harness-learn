"""LLM 和工具配置的只读查询路由。"""

from fastapi import APIRouter, Depends, Query

from ..dependencies import ApplicationServices, get_services
from ..schemas.common import ListResponse, Pagination
from ..schemas.settings import LLMProfileSummary, ToolSummary


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm-profiles", response_model=ListResponse[LLMProfileSummary])
async def list_llm_profiles(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> ListResponse[LLMProfileSummary]:
    """分页返回不含凭据引用和值的 LLM 配置。"""
    profiles = services.llm_profiles.list_all(limit + 1, offset)
    has_more = len(profiles) > limit
    items = [
        LLMProfileSummary(
            id=profile.id,
            name=profile.name,
            provider=profile.provider,
            base_url=profile.base_url,
            model=profile.model,
            # credential_ref 是配置引用而非密钥，但也不属于浏览器所需字段。
            has_credential=bool(profile.credential_ref),
            options=profile.options,
        )
        for profile in profiles[:limit]
    ]
    return ListResponse(
        items=items,
        pagination=Pagination(limit=limit, offset=offset, has_more=has_more),
    )


@router.get("/tools")
async def list_tools(
    services: ApplicationServices = Depends(get_services),
) -> dict[str, list[ToolSummary]]:
    """返回受信任工具的可展示元数据，不暴露 Python 对象。"""
    items = []
    for metadata in services.tool_catalog.list_available():
        schema = metadata.schema
        action = getattr(metadata.permission, "action", None)
        items.append(
            ToolSummary(
                name=metadata.name,
                description=schema.get("description", ""),
                input_schema=schema.get("parameters", {}),
                permission_action=getattr(action, "value", str(action or "")),
            )
        )
    return {"items": items}
