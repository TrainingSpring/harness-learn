import json
import os
from base64 import b64encode

from runtime.ExecutionContext import ExecutionContext
from tools.catalog import ToolCatalog
from permission.types import PermissionRequest
from tools.types import (
    Attachment,
    PreparedToolCall,
    Tool,
    ToolCallPreparationError,
    ToolError,
    ToolResult,
)


class Tools:
    """管理工具注册、调用准备、执行和 Responses 结果编码。"""
    def __init__(self,ctx:ExecutionContext):
        self.ctx = ctx
        self.map:dict[str,Tool] = {}
        self.list:list[dict] = []


    def register(self,tool:Tool):
        """
        注册工具
        :param tool : Tool : 工具
        :return : list[dict] :  工具集
        """
        name = tool.schema.get("name","")
        if not self.map.get(name):
            self.map[name] = tool
            self.list.append(tool.schema)

        return self.list

    def batch_register(self,tools:list[Tool]):
        """
        批量注册工具
        :param tools : list[tool] : 工具集
        :return : list[dict] : 工具集
        """
        for tool in tools:
            self.register(tool)
        return self.list

    def get_tools(self):
        return self.list
    def get_tool(self,name):
        try:
            return self.map[name]
        except KeyError:
            raise KeyError(f"工具不存在: {name}")

    def prepare_call(
        self,
        name: str,
        arguments: str | dict | None,
        call_id: str,
    ) -> PreparedToolCall:
        """解析一次模型工具调用，并生成待检查的权限请求。

        Args:
            name: 模型请求调用的工具名称。
            arguments: JSON 字符串或参数字典；None 表示空对象。
            call_id: 模型 function_call 的唯一标识。

        Returns:
            已解析的 PreparedToolCall，供 Runtime 先检查权限再执行。

        Raises:
            ToolCallPreparationError: 工具不存在、参数非法或资源参数缺失。

        参数在此处只解析一次。这样权限判断和真正执行共享同一份参数，
        不会因为重复 JSON 解析导致两条路径的行为不一致。
        """
        tool = self.map.get(name)
        if tool is None:
            raise ToolCallPreparationError(
                ToolError("TOOL_NOT_FOUND", f"工具不存在: {name}")
            )

        try:
            args = {} if arguments is None else (
                json.loads(arguments) if isinstance(arguments, str) else arguments
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ToolCallPreparationError(
                ToolError("INVALID_ARGUMENTS", str(error))
            ) from error

        if not isinstance(args, dict):
            raise ToolCallPreparationError(
                ToolError("INVALID_ARGUMENTS", "工具参数必须是 JSON 对象")
            )

        try:
            request = self.build_permission_request(tool, name, args, call_id)
        except (KeyError, TypeError, ValueError) as error:
            raise ToolCallPreparationError(
                ToolError("INVALID_ARGUMENTS", str(error))
            ) from error

        return PreparedToolCall(call_id, name, tool, args, request)

    def build_permission_request(
        self,
        tool: Tool,
        tool_name: str,
        arguments: dict,
        call_id: str,
    ) -> PermissionRequest:
        """根据工具权限声明和已解析参数构造真实权限请求。

        Args:
            tool: 已注册工具定义。
            tool_name: 工具名称，供用户确认界面和诊断使用。
            arguments: 已验证为对象的工具参数。
            call_id: 当前模型工具调用标识。

        Returns:
            带规范化资源与执行身份的 PermissionRequest。
        """
        resource = None
        resource_from = tool.permission.resource_from
        if resource_from is not None:
            raw_resource = arguments[resource_from]
            if not isinstance(raw_resource, str) or not raw_resource:
                raise TypeError(f"权限资源参数 {resource_from} 必须是非空字符串")
            resource = os.path.normpath(
                os.path.abspath(self._resolve_path(raw_resource))
            )

        return PermissionRequest(
            action=tool.permission.action,
            resource=resource,
            tool_name=tool_name,
            call_id=call_id,
            session_id=self.ctx.session_id,
            agent_key=self.ctx.agent_key,
        )

    def execute(self, call: PreparedToolCall) -> ToolResult:
        """执行已经完成权限预检的工具调用。

        Args:
            call: 已准备的工具调用；权限决定由 Runtime 在此之前完成。

        Returns:
            工具返回的 ToolResult，或由执行异常转换出的失败结果。
        """
        try:
            result = call.tool.function(self.ctx, **call.arguments)
        except Exception as error:
            return ToolResult.failure("TOOL_EXECUTION_FAILED", str(error))

        if not isinstance(result, ToolResult):
            return ToolResult.failure(
                "INVALID_TOOL_RESULT",
                f"工具 {call.tool_name} 必须返回 ToolResult",
            )
        return result

    def default_grant_resource(self, request: PermissionRequest) -> str | None:
        """计算用户确认后默认写入的授权资源范围。

        Args:
            request: 当前真实权限请求。

        Returns:
            文件请求返回目标父目录，bash 等无资源动作返回 None。

        这里仅决定授权范围，不负责判断是否安全；安全判断始终由
        PermissionManager 完成。
        """
        if request.resource is None:
            return None
        return os.path.dirname(request.resource)

    def _resolve_path(self, target_path: str) -> str:
        """将工具路径参数解析为基于当前 workspace 的路径。"""
        if os.path.isabs(target_path):
            return target_path
        return os.path.join(self.ctx.workspace, target_path)

    @staticmethod
    def encode_result(result):
        """将内部 ToolResult 适配为 Responses function_call_output.output。

        这是工具层唯一可以产生 input_text、input_image 等 Responses
        协议字段的位置。工具实现只处理 ToolResult 和 Attachment。
        """
        if not isinstance(result, ToolResult):
            raise TypeError("工具结果必须是 ToolResult")

        if result.attachments:
            # 多模态输出必须使用 content 数组；业务数据仍作为首个文本项。
            content = [{
                "type": "input_text",
                "text": Tools._serialize_value(Tools._result_data(result)),
            }]
            for attachment in result.attachments:
                content.append(Tools._encode_attachment(attachment))
            return content

        return Tools._serialize_value(Tools._result_data(result))

    @staticmethod
    def _encode_attachment(attachment: Attachment):
        """根据 MIME 类型和来源将内部附件转换成 Responses 内容项。"""
        if attachment.media_type.startswith("image/"):
            image_url = Tools._attachment_source(attachment)
            return {
                "type": "input_image",
                "image_url": image_url,
                "detail": "auto",
            }

        raise ValueError(f"暂不支持的附件类型: {attachment.media_type}")

    @staticmethod
    def _attachment_source(attachment: Attachment):
        if attachment.source_kind == "url":
            return attachment.source
        encoded = b64encode(attachment.source).decode("ascii")
        return f"data:{attachment.media_type};base64,{encoded}"

    @staticmethod
    def _result_data(result: ToolResult):
        """将统一结果投影为可 JSON 序列化的工具响应主体。"""
        if result.status == "ok":
            return {"status": result.status, "data": result.data}
        return {
            "status": result.status,
            "error": {
                "code": result.error.code,
                "message": result.error.message,
                "retryable": result.error.retryable,
                **({"details": result.error.details} if result.error.details else {}),
            },
        }

    @staticmethod
    def _serialize_value(value):
        # 普通函数工具输出必须是字符串；结构化数据使用 JSON 字符串承载。
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False)

    def register_by_names(self,names:list[str]):
        """
        根据名称注册工具
        :param names : list[str] : 工具名称列表
        :return : list[dict] : 工具集
        """
        catalog = ToolCatalog()
        for name in names:
            self.register(catalog.get(name))
        return self
