"""设置页面的查询和创建 DTO。"""

from typing import Any, Literal

from pydantic import Field

from .common import ApiModel


class LLMProfileSummary(ApiModel):
    """不含 API Key 的 LLM 配置摘要。"""

    id: str
    name: str
    protocol: Literal["responses", "completions", "claude"]
    base_url: str | None
    model: str
    has_api_key: bool
    options: dict[str, Any]


class ApiKeyResponse(ApiModel):
    """仅用于编辑 LLM 配置时回显的 API Key。"""

    api_key: str


class CreateLLMProfileRequest(ApiModel):
    """创建 LLM 配置时提交并持久化的连接参数。"""

    name: str = Field(min_length=1)
    protocol: Literal["responses", "completions", "claude"] = "responses"
    base_url: str | None = None
    model: str = Field(min_length=1)
    api_key: str = Field(min_length=1)
    options: dict[str, Any] = Field(default_factory=dict)


class UpdateLLMProfileRequest(ApiModel):
    """更新 LLM 配置时提交的字段。

    ``api_key`` 是可选字段，编辑时留空表示沿用数据库中的原密钥。
    """

    name: str = Field(min_length=1)
    protocol: Literal["responses", "completions", "claude"] = "responses"
    base_url: str | None = None
    model: str = Field(min_length=1)
    api_key: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ModelDiscoveryRequest(ApiModel):
    """根据尚未保存的表单连接参数读取模型列表。"""

    protocol: Literal["responses", "completions", "claude"] = "responses"
    base_url: str | None = None
    api_key: str = Field(min_length=1)


class ModelListResponse(ApiModel):
    """服务商返回的可选模型 ID。"""

    models: list[str]


class ToolSummary(ApiModel):
    """供设置页展示的受信任工具元数据。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    permission_action: str


class SkillSummary(ApiModel):
    """供设置页和角色配置页使用的 Skill 索引摘要。"""

    id: str
    name: str
    description: str
    license: str | None
    compatibility: str | None
    status: Literal["AVAILABLE", "INVALID", "MISSING"]
    validation_error: str | None
    agent_count: int
    updated_at: str | None


class SkillSyncResult(ApiModel):
    """一次 Skill 刷新的统计结果。"""

    added: int
    updated: int
    unchanged: int
    missing: int
    invalid: int
    items: list[SkillSummary]


class McpServerSummary(ApiModel):
    """MCP Server 的公开配置和运行状态，不包含连接对象或令牌。"""

    id: str
    name: str
    description: str
    is_local: bool
    transport: Literal["stdio", "streamable_http"]
    enabled: bool
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth_mode: Literal["none", "bearer", "oauth"] = "none"
    status: str
    instance_id: str | None = None
    pid: int | None = None
    diagnostic_code: str | None = None
    diagnostics: list[str] = Field(default_factory=list)


class McpServerListResponse(ApiModel):
    """MCP Server 列表和配置 revision。"""

    items: list[McpServerSummary]
    revision: str


class CreateMcpServerRequest(ApiModel):
    """新增 MCP Server 的联合配置请求。"""

    name: str = Field(min_length=1, max_length=8192)
    description: str = ""
    is_local: bool
    enabled: bool = True
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    auth_mode: Literal["none", "bearer", "oauth"] = "none"
    startup_timeout_ms: int = Field(default=10000, ge=100, le=300000)
    shutdown_timeout_ms: int = Field(default=5000, ge=100, le=300000)
    request_timeout_ms: int = Field(default=30000, ge=100, le=300000)


class UpdateMcpServerRequest(CreateMcpServerRequest):
    """编辑 MCP Server 的完整配置，要求携带当前 revision。"""

    revision: str = Field(min_length=1)


class McpServerActionResponse(ApiModel):
    """MCP 本地生命周期操作后的状态。"""

    item: McpServerSummary
