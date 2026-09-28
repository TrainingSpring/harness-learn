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


class McpProtocolError(McpError):
    """收到不符合 JSON-RPC 或 MCP Transport 约束的消息。"""

    code = "MCP_PROTOCOL_ERROR"


class McpRemoteError(McpError):
    """远端 MCP Server 返回的 JSON-RPC error。"""

    code = "MCP_REMOTE_ERROR"

    def __init__(self, remote_code: int, message: str, data: object = None) -> None:
        super().__init__(message)
        self.remote_code = remote_code
        self.data = data


class McpTransportError(McpError):
    """底层 stdio 或 HTTP 连接无法完成一次 MCP 传输。"""

    code = "MCP_TRANSPORT_ERROR"


class McpTransportTimeoutError(McpTransportError):
    """请求在调用方限定的时间内没有得到 MCP 响应。"""

    code = "MCP_TRANSPORT_TIMEOUT"


class McpRequestCancelledError(McpTransportError):
    """调用方取消了尚未完成的 MCP 请求。"""

    code = "MCP_REQUEST_CANCELLED"


class McpConnectionClosedError(McpTransportError):
    """MCP 连接在请求结束前关闭。"""

    code = "MCP_CONNECTION_CLOSED"


class McpSessionExpiredError(McpTransportError):
    """Streamable HTTP Server 拒绝当前会话，Client 应重新初始化。"""

    code = "MCP_SESSION_EXPIRED"


class McpLocalServerError(McpError):
    """本地 MCP Server 生命周期操作失败。"""

    code = "MCP_LOCAL_SERVER_ERROR"


class McpRemoteLifecycleError(McpError):
    """尝试对远程 MCP Server 执行本地进程操作。"""

    code = "MCP_REMOTE_LIFECYCLE_UNSUPPORTED"


class McpProcessManagerClosedError(McpLocalServerError):
    """进程管理器已经关闭。"""

    code = "MCP_PROCESS_MANAGER_CLOSED"


class McpLifecycleError(McpError):
    """MCP initialize、协商或关闭生命周期失败。"""

    code = "MCP_LIFECYCLE_ERROR"


class McpCapabilityUnavailableError(McpError):
    """Server 没有声明客户端即将使用的 MCP 能力。"""

    code = "MCP_CAPABILITY_UNAVAILABLE"


class McpPaginationError(McpError):
    """分页响应缺失字段、循环 cursor 或超过受控页数。"""

    code = "MCP_PAGINATION_ERROR"


class McpConnectionManagerClosedError(McpError):
    """连接管理器关闭后继续请求连接。"""

    code = "MCP_CONNECTION_MANAGER_CLOSED"
