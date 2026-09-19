"""LLM 创建及工具、LLM 配置查询路由。"""

from fastapi import APIRouter, Depends, Query, status

from storage.errors import StorageConflictError
from storage.ids import generate_id
from storage.types import LLMProfile

from ..dependencies import ApplicationServices, get_services
from ..errors import ApiError
from ..schemas.common import ListResponse, Pagination
from ..schemas.settings import (
    CreateLLMProfileRequest,
    LLMProfileSummary,
    ModelDiscoveryRequest,
    ModelListResponse,
    ToolSummary,
    UpdateLLMProfileRequest,
)
from ..services.llm_model_discovery import ModelDiscoveryError, discover_models


router = APIRouter(prefix="/settings", tags=["settings"])


def _llm_summary(profile: LLMProfile) -> LLMProfileSummary:
    """将内部 LLM 配置转换为不含 API Key 的摘要。"""
    return LLMProfileSummary(
        id=profile.id,
        name=profile.name,
        provider=profile.provider,
        base_url=profile.base_url,
        model=profile.model,
        has_api_key=bool(profile.api_key),
        options=profile.options,
    )


@router.get("/llm-profiles", response_model=ListResponse[LLMProfileSummary])
async def list_llm_profiles(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    services: ApplicationServices = Depends(get_services),
) -> ListResponse[LLMProfileSummary]:
    """分页返回不含 API Key 的 LLM 配置。"""
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
    """创建一套可供角色引用的 LLM 配置，并返回脱敏摘要。"""
    profile = LLMProfile(
        id=generate_id("llm"),
        name=request.name,
        provider=request.provider,
        base_url=request.base_url,
        model=request.model,
        api_key=request.api_key,
        options=request.options,
    )
    try:
        saved = services.llm_profiles.save(profile)
    except StorageConflictError as error:
        raise ApiError(409, "LLM_PROFILE_CONFLICT", "LLM 配置名称已存在") from error
    return _llm_summary(saved)


@router.patch(
    "/llm-profiles/{profile_id}",
    response_model=LLMProfileSummary,
)
async def update_llm_profile(
    profile_id: str,
    request: UpdateLLMProfileRequest,
    services: ApplicationServices = Depends(get_services),
) -> LLMProfileSummary:
    """更新一套 LLM 配置并返回脱敏摘要。"""
    try:
        current = services.llm_profiles.get(profile_id)
    except ValueError as error:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在") from error
    if current is None:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在")

    profile = LLMProfile(
        id=current.id,
        name=request.name,
        provider=request.provider,
        base_url=request.base_url,
        model=request.model,
        api_key=request.api_key or current.api_key,
        options=request.options,
        created_at=current.created_at,
    )
    try:
        saved = services.llm_profiles.save(profile)
    except StorageConflictError as error:
        raise ApiError(409, "LLM_PROFILE_CONFLICT", "LLM 配置名称已存在") from error
    return _llm_summary(saved)


@router.post("/llm-profiles/models", response_model=ModelListResponse)
async def discover_draft_models(request: ModelDiscoveryRequest) -> ModelListResponse:
    """用尚未保存的表单参数获取可选模型。"""
    try:
        models = await discover_models(request.provider, request.base_url, request.api_key)
    except ModelDiscoveryError as error:
        raise ApiError(502, "MODEL_DISCOVERY_FAILED", str(error)) from error
    return ModelListResponse(models=models)


@router.get("/llm-profiles/{profile_id}/models", response_model=ModelListResponse)
async def discover_saved_models(
    profile_id: str,
    services: ApplicationServices = Depends(get_services),
) -> ModelListResponse:
    """用数据库中保存的 API Key 获取指定配置的可选模型。"""
    try:
        profile = services.llm_profiles.get(profile_id)
    except ValueError as error:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在") from error
    if profile is None:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在")
    if not profile.api_key:
        raise ApiError(400, "API_KEY_REQUIRED", "请先填写 API Key")
    try:
        models = await discover_models(profile.provider, profile.base_url, profile.api_key)
    except ModelDiscoveryError as error:
        raise ApiError(502, "MODEL_DISCOVERY_FAILED", str(error)) from error
    return ModelListResponse(models=models)


@router.delete("/llm-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_profile(
    profile_id: str,
    services: ApplicationServices = Depends(get_services),
) -> None:
    """删除未被 Agent 引用的 LLM 配置。"""
    try:
        deleted = services.llm_profiles.delete(profile_id)
    except ValueError as error:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在") from error
    except StorageConflictError as error:
        raise ApiError(409, "LLM_PROFILE_IN_USE", "LLM 配置仍被角色使用，不能删除") from error
    if not deleted:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在")


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
