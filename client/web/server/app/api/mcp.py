"""MCP Server 配置和本地生命周期管理路由。"""

from fastapi import APIRouter, Depends, status

from mcp.config_store import McpConfigStore
from mcp.errors import (
    McpConfigConflictError,
    McpConfigFormatError,
    McpLocalServerError,
    McpRemoteLifecycleError,
    McpServerDisabledError,
    McpServerNotFoundError,
)
from mcp.process_manager import McpLocalServerState, McpProcessManager
from mcp.types import LocalMcpServerConfig, McpServerConfig, RemoteMcpServerConfig
from mcp.oauth import OAuthClient, OAuthMetadata
from storage.ids import generate_id

from ..dependencies import ApplicationServices, get_services
from ..errors import ApiError
from ..schemas.settings import (
    CreateMcpServerRequest,
    McpServerActionResponse,
    McpServerListResponse,
    McpServerSummary,
    UpdateMcpServerRequest,
)


router = APIRouter(prefix="/settings/mcp", tags=["mcp"])


def _oauth_metadata(server: RemoteMcpServerConfig, services: ApplicationServices) -> OAuthMetadata:
    # Metadata discovery remains an explicit user action; it never runs during list.
    from mcp.oauth import OAuthClient
    client = OAuthClient(
        client_id=server.oauth_client_id or "harness-learn",
        redirect_uri="http://127.0.0.1:8765/oauth/mcp/callback",
        scopes=server.oauth_scopes,
        resource=server.url,
    )
    try:
        return client.discover(server.url)
    finally:
        client.close()


def _oauth_client(server: RemoteMcpServerConfig) -> OAuthClient:
    return OAuthClient(
        client_id=server.oauth_client_id or "harness-learn",
        redirect_uri="http://127.0.0.1:8765/oauth/mcp/callback",
        scopes=server.oauth_scopes,
        resource=server.url,
    )


@router.get("/oauth/callback")
async def oauth_callback(
    authorization_id: str,
    code: str,
    state: str,
    services: ApplicationServices = Depends(get_services),
) -> dict[str, str]:
    try:
        services.mcp_authorization.complete(authorization_id, code=code, state=state)
    except Exception as error:
        raise ApiError(400, getattr(error, "code", "MCP_AUTH_FAILED"), "OAuth 授权回调失败") from error
    return {"status": "authorized"}


@router.get("/{server_id}/oauth/start")
async def oauth_start(server_id: str, services: ApplicationServices = Depends(get_services)) -> dict[str, str]:
    try:
        server = services.mcp_servers.get(server_id)
    except McpServerNotFoundError as error:
        raise ApiError(404, error.code, "MCP Server 不存在") from error
    if not isinstance(server, RemoteMcpServerConfig) or server.auth_mode != "oauth":
        raise ApiError(409, "MCP_AUTH_REQUIRED", "当前 MCP Server 未启用 OAuth")
    client = _oauth_client(server)
    try:
        metadata = _oauth_metadata(server, services)
        authorization_id, url = services.mcp_authorization.begin(server.id, client, metadata)
    except Exception as error:
        client.close()
        raise ApiError(409, getattr(error, "code", "MCP_AUTH_FAILED"), "无法发起 OAuth 授权") from error
    return {"authorizationId": authorization_id, "authorizationUrl": url}


@router.get("/{server_id}/oauth/status", response_model=McpServerSummary)
async def oauth_status(server_id: str, services: ApplicationServices = Depends(get_services)) -> McpServerSummary:
    try:
        server = services.mcp_servers.get(server_id)
    except McpServerNotFoundError as error:
        raise ApiError(404, error.code, "MCP Server 不存在") from error
    return _summary(server, services)


@router.post("/{server_id}/oauth/revoke", response_model=McpServerSummary)
async def oauth_revoke(server_id: str, services: ApplicationServices = Depends(get_services)) -> McpServerSummary:
    try:
        server = services.mcp_servers.get(server_id)
    except McpServerNotFoundError as error:
        raise ApiError(404, error.code, "MCP Server 不存在") from error
    if not isinstance(server, RemoteMcpServerConfig) or server.auth_mode != "oauth":
        raise ApiError(409, "MCP_AUTH_REQUIRED", "当前 MCP Server 未启用 OAuth")
    metadata = _oauth_metadata(server, services)
    client = _oauth_client(server)
    try:
        services.mcp_authorization.revoke(server.id, client, metadata)
    except Exception as error:
        raise ApiError(409, getattr(error, "code", "MCP_AUTH_FAILED"), "OAuth 撤销失败") from error
    finally:
        client.close()
    return _summary(server, services)


def _status_for(server: McpServerConfig, services: ApplicationServices) -> McpServerSummary:
    data = {
        "id": server.id,
        "name": server.name,
        "description": server.description,
        "is_local": server.is_local,
        "transport": server.transport,
        "enabled": server.enabled,
        "status": "remote" if not server.is_local else McpLocalServerState.NOT_RUNNING.value,
        "instance_id": None,
        "pid": None,
        "diagnostic_code": None,
        "diagnostics": [],
    }
    if isinstance(server, LocalMcpServerConfig):
        data.update(command=server.command, args=list(server.args), cwd=server.cwd, env=dict(server.env))
        try:
            current = services.mcp_processes.status(server.id)
        except (McpRemoteLifecycleError, McpServerNotFoundError):
            current = None
        if current is not None:
            data.update(
                status=current.state.value,
                instance_id=current.instance_id,
                pid=current.pid,
                diagnostic_code=current.diagnostic_code,
                diagnostics=list(current.diagnostics),
            )
    else:
        data.update(url=server.url, headers=dict(server.headers), auth_mode=server.auth_mode)
        if server.auth_mode == "oauth":
            auth = services.mcp_authorization.status(server.id)
            data.update(
                oauth_authorized=auth.authorized,
                oauth_expires_at=auth.expires_at,
                oauth_error=auth.error,
            )
    return McpServerSummary(**data)


def _summary(server: McpServerConfig, services: ApplicationServices) -> McpServerSummary:
    summary = _status_for(server, services)
    if isinstance(server, RemoteMcpServerConfig):
        summary.headers = {
            name: "[REDACTED]" if name.casefold() in {"authorization", "x-api-key", "api-key"} else value
            for name, value in server.headers.items()
        }
    return summary


def _build_config(server_id: str, request: CreateMcpServerRequest) -> McpServerConfig:
    if request.is_local:
        if not request.command:
            raise ApiError(422, "MCP_CONFIG_INVALID", "本地 MCP 必须填写 command")
        if request.url is not None:
            raise ApiError(422, "MCP_CONFIG_INVALID", "本地 MCP 不能填写 url")
        return LocalMcpServerConfig(
            id=server_id, name=request.name, description=request.description,
            command=request.command, args=request.args, cwd=request.cwd, env=request.env,
            enabled=request.enabled, startup_timeout_ms=request.startup_timeout_ms,
            shutdown_timeout_ms=request.shutdown_timeout_ms,
        )
    if not request.url:
        raise ApiError(422, "MCP_CONFIG_INVALID", "远程 MCP 必须填写 url")
    if request.command is not None or request.args or request.cwd is not None or request.env:
        raise ApiError(422, "MCP_CONFIG_INVALID", "远程 MCP 不能填写本地进程字段")
    return RemoteMcpServerConfig(
        id=server_id, name=request.name, description=request.description,
        url=request.url, headers=request.headers, auth_mode=request.auth_mode,
        enabled=request.enabled, request_timeout_ms=request.request_timeout_ms,
        oauth_client_id=request.oauth_client_id,
        oauth_scopes=tuple(request.oauth_scopes),
    )


def _config_error(error: Exception) -> ApiError:
    if isinstance(error, McpConfigConflictError):
        return ApiError(409, error.code, "MCP 配置已被外部修改，请刷新后重试")
    if isinstance(error, McpServerNotFoundError):
        return ApiError(404, error.code, "MCP Server 不存在")
    if isinstance(error, McpConfigFormatError):
        return ApiError(422, error.code, str(error))
    return ApiError(500, "MCP_CONFIG_ERROR", "MCP 配置操作失败")


@router.get("", response_model=McpServerListResponse)
async def list_mcp_servers(services: ApplicationServices = Depends(get_services)) -> McpServerListResponse:
    snapshot = services.mcp_config_store.read()
    return McpServerListResponse(
        items=[_summary(server, services) for server in snapshot.document.servers],
        revision=snapshot.revision,
    )


@router.post("", response_model=McpServerSummary, status_code=status.HTTP_201_CREATED)
async def create_mcp_server(
    request: CreateMcpServerRequest,
    services: ApplicationServices = Depends(get_services),
) -> McpServerSummary:
    try:
        server = _build_config(generate_id("mcp"), request)
        saved = services.mcp_config_store.create(server)
        return _summary(saved.document.servers[-1], services)
    except ApiError:
        raise
    except Exception as error:
        raise _config_error(error) from error


@router.put("/{server_id}", response_model=McpServerSummary)
async def update_mcp_server(
    server_id: str,
    request: UpdateMcpServerRequest,
    services: ApplicationServices = Depends(get_services),
) -> McpServerSummary:
    try:
        server = _build_config(server_id, request)
        saved = services.mcp_config_store.update(server, expected_revision=request.revision)
        return _summary(next(item for item in saved.document.servers if item.id == server_id), services)
    except ApiError:
        raise
    except Exception as error:
        raise _config_error(error) from error


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mcp_server(server_id: str, revision: str, services: ApplicationServices = Depends(get_services)) -> None:
    try:
        server = services.mcp_servers.get(server_id)
        if isinstance(server, LocalMcpServerConfig):
            try:
                services.mcp_processes.stop(server_id)
            except McpLocalServerError:
                pass
        services.mcp_connections.close_server(server_id)
        services.mcp_config_store.delete(server_id, expected_revision=revision)
    except Exception as error:
        raise _config_error(error) from error


def _action(server_id: str, action: str, services: ApplicationServices) -> McpServerActionResponse:
    try:
        server = services.mcp_servers.get(server_id)
        if not isinstance(server, LocalMcpServerConfig):
            raise McpRemoteLifecycleError("远程 MCP Server 不支持本地生命周期操作")
        result = getattr(services.mcp_processes, action)(server_id)
        return McpServerActionResponse(item=_summary(server, services))
    except (McpRemoteLifecycleError, McpServerDisabledError) as error:
        raise ApiError(409, error.code, str(error)) from error
    except Exception as error:
        raise ApiError(409, getattr(error, "code", "MCP_LOCAL_SERVER_ERROR"), str(error)) from error


@router.post("/{server_id}/start", response_model=McpServerActionResponse)
async def start_mcp_server(server_id: str, services: ApplicationServices = Depends(get_services)) -> McpServerActionResponse:
    return _action(server_id, "start", services)


@router.post("/{server_id}/stop", response_model=McpServerActionResponse)
async def stop_mcp_server(server_id: str, services: ApplicationServices = Depends(get_services)) -> McpServerActionResponse:
    return _action(server_id, "stop", services)


@router.post("/{server_id}/restart", response_model=McpServerActionResponse)
async def restart_mcp_server(server_id: str, services: ApplicationServices = Depends(get_services)) -> McpServerActionResponse:
    return _action(server_id, "restart", services)
