"""LLM 创建及工具、LLM 配置查询路由。"""

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
import io
import zipfile
from pathlib import Path

from storage.errors import StorageConflictError
from storage.ids import generate_id
from storage.types import LLMProfile

from ..config import DEFAULT_DATA_DIR, load_data_dir, save_data_dir
from ..dependencies import ApplicationServices, get_services
from ..errors import ApiError
from ..schemas.common import ListResponse, Pagination
from ..schemas.settings import (
    ApiKeyResponse,
    CreateLLMProfileRequest,
    LLMProfileSummary,
    ModelDiscoveryRequest,
    ModelListResponse,
    StorageDirectory,
    StorageDirectoryListResponse,
    StorageSettingsResponse,
    ToolSummary,
    SkillSummary,
    SkillSyncResult,
    UpdateLLMProfileRequest,
    UpdateStorageSettingsRequest,
)
from ..services.llm_model_discovery import ModelDiscoveryError, discover_models


router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/storage", response_model=StorageSettingsResponse)
async def get_storage_settings() -> StorageSettingsResponse:
    """返回当前应用数据目录。"""
    return StorageSettingsResponse(data_dir=str(load_data_dir()), default_data_dir=str(DEFAULT_DATA_DIR))


@router.put("/storage", response_model=StorageSettingsResponse)
async def update_storage_settings(
    request: UpdateStorageSettingsRequest,
) -> StorageSettingsResponse:
    """设置下次启动的数据目录，并标记需要重启后迁移。"""
    current = load_data_dir()
    try:
        target = save_data_dir(request.data_dir, migration_source=current)
    except (OSError, ValueError) as error:
        raise ApiError(422, "INVALID_DATA_DIR", "存储目录不可用") from error
    return StorageSettingsResponse(
        data_dir=str(target),
        default_data_dir=str(DEFAULT_DATA_DIR),
        restart_required=True,
    )


@router.get("/directories", response_model=StorageDirectoryListResponse)
async def list_storage_directories(
    path: str = Query(default=".", max_length=2000),
) -> StorageDirectoryListResponse:
    """列出可选的本机数据目录，供基础设置中的目录选择器使用。"""
    try:
        directory = Path(path).expanduser().resolve(strict=True)
        if not directory.is_dir():
            raise ValueError("存储目录必须是目录")
        children = [
            StorageDirectory(path=str(child.resolve()), name=child.name)
            for child in sorted(directory.iterdir(), key=lambda item: item.name.lower())
            if child.is_dir()
        ]
    except (OSError, ValueError) as error:
        raise ApiError(422, "INVALID_DATA_DIR", "存储目录不可用") from error

    parent = directory.parent if directory.parent != directory else None
    return StorageDirectoryListResponse(
        path=str(directory),
        name=directory.name or str(directory),
        parent_path=None if parent is None else str(parent),
        directories=children,
    )


def _llm_summary(profile: LLMProfile) -> LLMProfileSummary:
    """将内部 LLM 配置转换为不含 API Key 的摘要。"""
    return LLMProfileSummary(
        id=profile.id,
        name=profile.name,
        protocol=profile.protocol,
        base_url=profile.base_url,
        model=profile.model,
        has_api_key=bool(profile.api_key),
        options=profile.options,
    )


@router.get("/llm-profiles/{profile_id}/api-key", response_model=ApiKeyResponse)
async def get_llm_profile_api_key(
    profile_id: str,
    services: ApplicationServices = Depends(get_services),
) -> ApiKeyResponse:
    """返回指定 LLM 配置的 API Key，供本地编辑表单默认遮蔽回显。"""
    try:
        profile = services.llm_profiles.get(profile_id)
    except ValueError as error:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在") from error
    if profile is None:
        raise ApiError(404, "LLM_PROFILE_NOT_FOUND", "LLM 配置不存在")
    return ApiKeyResponse(api_key=profile.api_key)


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
        protocol=request.protocol,
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
        protocol=request.protocol,
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
        models = await discover_models(request.protocol, request.base_url, request.api_key)
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
        models = await discover_models(profile.protocol, profile.base_url, profile.api_key)
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


def _skill_summary(profile, services: ApplicationServices) -> SkillSummary:
    return SkillSummary(
        id=profile.id,
        name=profile.name,
        description=profile.description,
        license=profile.license,
        compatibility=profile.compatibility,
        status=profile.status,
        validation_error=profile.validation_error,
        agent_count=services.skill_profiles.count_agents(profile.id),
        updated_at=profile.updated_at,
    )


@router.get("/skills", response_model=ListResponse[SkillSummary])
async def list_skills(
    services: ApplicationServices = Depends(get_services),
) -> ListResponse[SkillSummary]:
    """只从数据库读取已同步的 Skill 索引。"""
    items = [_skill_summary(skill, services) for skill in services.skill_profiles.list_all()]
    return ListResponse(
        items=items,
        pagination=Pagination(limit=len(items), offset=0, has_more=False),
    )


@router.post("/skills/refresh", response_model=SkillSyncResult)
async def refresh_skills(
    services: ApplicationServices = Depends(get_services),
) -> SkillSyncResult:
    """扫描固定 Skill 目录并更新数据库索引。"""
    result = services.skill_sync_service.refresh()
    items = [_skill_summary(skill, services) for skill in services.skill_profiles.list_all()]
    return SkillSyncResult(
        added=result.added,
        updated=result.updated,
        unchanged=result.unchanged,
        missing=result.missing,
        invalid=result.invalid,
        items=items,
    )


@router.post("/skills/import", response_model=SkillSyncResult)
async def import_skill(
    file: UploadFile = File(...),
    services: ApplicationServices = Depends(get_services),
) -> SkillSyncResult:
    """导入 ZIP Skill 到固定目录后执行刷新。"""
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise ApiError(400, "SKILL_IMPORT_INVALID", "只支持 ZIP 格式的 Skill")
    payload = await file.read()
    if len(payload) > 20 * 1024 * 1024:
        raise ApiError(413, "SKILL_IMPORT_TOO_LARGE", "Skill 压缩包不能超过 20MB")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > 500:
                raise ValueError("Skill 文件数量超过限制")
            root = services.skill_catalog.root
            root.mkdir(parents=True, exist_ok=True)
            for member in members:
                path = Path(member.filename)
                if path.is_absolute() or ".." in path.parts or member.filename.startswith("/"):
                    raise ValueError("压缩包包含非法路径")
                if member.is_dir():
                    continue
                target = (root / path).resolve()
                if target != root and root not in target.parents:
                    raise ValueError("压缩包路径不能逃逸 Skills 目录")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
    except (zipfile.BadZipFile, OSError, ValueError) as error:
        raise ApiError(400, "SKILL_IMPORT_INVALID", "Skill 压缩包无法导入") from error
    result = services.skill_sync_service.refresh()
    items = [_skill_summary(skill, services) for skill in services.skill_profiles.list_all()]
    return SkillSyncResult(
        added=result.added, updated=result.updated, unchanged=result.unchanged,
        missing=result.missing, invalid=result.invalid, items=items,
    )
