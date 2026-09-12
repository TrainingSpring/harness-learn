"""LLM 创建及工具、LLM 配置查询路由。"""

from fastapi import APIRouter, Depends, Query, status

from storage.errors import StorageConflictError
from storage.ids import generate_id
from storage.types import LLMProfile

from ..dependencies import ApplicationServices, get_services
from ..errors import ApiError
from ..schemas.common import ListResponse, Pagination
from ..schemas.settings import CreateLLMProfileRequest, LLMProfileSummary, ToolSummary


router = APIRouter(prefix="/settings", tags=["settings"])


def _llm_summary(profile: LLMProfile) -> LLMProfileSummary:
    """将内部 LLM 配置转换为不含 credential_ref 的摘要。"""
    return LLMProfileSummary(
        id=profile.id,
        name=profile.name,
        provider=profile.provider,
        base_url=profile.base_url,
        model=profile.model,
        has_credential=bool(profile.credential_ref),
        options=profile.options,
    )


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
        _llm_summary(profile)
        for profile in profiles[:limit]
    ]
    return ListResponse(
        items=items,
        pagination=Pagination(limit=limit, offset=offset, has_more=has_more),
    )


@router.post(
    "/llm-profiles",
    response_model=LLMProfileSummary,
    status_code=status.HTTP_201_CREATED,
)
async def create_llm_profile(
    request: CreateLLMProfileRequest,
    services: ApplicationServices = Depends(get_services),
) -> LLMProfileSummary:
    """创建一套可供角色引用的 LLM 配置。

    请求中的 credential_ref 仅作为凭据定位引用持久化，响应始终返回脱敏摘要。
    """
    profile = LLMProfile(
        id=generate_id("llm"),
        name=request.name,
        provider=request.provider,
        base_url=request.base_url,
        model=request.model,
        credential_ref=request.credential_ref,
        options=request.options,
    )
    try:
        saved = services.llm_profiles.save(profile)
    except StorageConflictError as error:
        raise ApiError(409, "LLM_PROFILE_CONFLICT", "LLM 配置名称已存在") from error
    return _llm_summary(saved)


@router.get("/tools", response_model=ListResponse[ToolSummary])
async def list_tools(
    services: ApplicationServices = Depends(get_services),
) -> ListResponse[ToolSummary]:
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
    return ListResponse(
        items=items,
        # 工具目录当前是本地受信列表，不提供动态分页。但仍使用统一外壳，让前端不需要为特殊接口写分支。
        pagination=Pagination(limit=len(items), offset=0, has_more=False),
    )
