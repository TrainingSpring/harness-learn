"""稳定的 MCP 配置和注册表错误。"""


class McpError(Exception):
    """MCP 子系统错误基类。"""

    code = "MCP_ERROR"


class McpConfigError(McpError):
    """配置文件读取、校验或写入错误。"""


class McpConfigFormatError(McpConfigError):
    """配置文件不是有效的 MCP 配置文档。"""

    code = "MCP_CONFIG_INVALID"


class McpConfigConflictError(McpConfigError):
    """写入基于已过期的配置 revision。"""

    code = "MCP_CONFIG_CONFLICT"


class McpServerNotFoundError(McpError):
    """注册表中不存在指定 MCP Server。"""

    code = "MCP_SERVER_NOT_FOUND"


class McpServerDisabledError(McpError):
    """指定 MCP Server 已禁用。"""

    code = "MCP_SERVER_DISABLED"
