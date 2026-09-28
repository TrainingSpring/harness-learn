"""Server -> Client MCP 请求的受控处理器。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .errors import McpCapabilityUnavailableError, McpProtocolError
from .elicitation import validate_elicitation_request, validate_elicitation_result
from .protocol import JsonRpcError, JsonRpcRequest, JsonRpcResponse
from .roots import roots_for_workspace
from .sampling import validate_sampling_request, validate_sampling_result


RequestCallback = Callable[[dict[str, Any]], dict[str, Any]]


class McpServerRequestHandler:
    """只处理显式注册的 roots、sampling、elicitation 请求。"""

    def __init__(self, *, workspace: str | None = None) -> None:
        self.workspace = workspace
        self._handlers: dict[str, RequestCallback] = {}

    def register(self, method: str, callback: RequestCallback) -> None:
        if method not in {"sampling/createMessage", "elicitation/create"}:
            raise ValueError("不允许注册未知 MCP Server request")
        if not callable(callback):
            raise TypeError("callback 必须可调用")
        self._handlers[method] = callback

    def handle(self, request: JsonRpcRequest) -> JsonRpcResponse:
        try:
            params = request.params if isinstance(request.params, dict) else {}
            if request.method == "roots/list":
                result = {"roots": [root.to_dict() for root in roots_for_workspace(self.workspace)]}
            elif request.method in self._handlers:
                if request.method == "sampling/createMessage":
                    request_params = validate_sampling_request(params)
                    result = validate_sampling_result(self._handlers[request.method](request_params))
                else:
                    request_params = validate_elicitation_request(params)
                    result = validate_elicitation_result(self._handlers[request.method](request_params))
            else:
                raise McpCapabilityUnavailableError(f"MCP Client 不支持 Server request: {request.method}")
            return JsonRpcResponse(id=request.id, result=result)
        except Exception as error:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(-32601 if isinstance(error, McpCapabilityUnavailableError) else -32602, str(error)),
            )
