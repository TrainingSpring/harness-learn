import importlib
import json
from base64 import b64encode

from runtime.ExecutionContext import ExecutionContext
from tools.types import Attachment, Tool, ToolResult


class Tools:
    """
    工具集
    """
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

    def eval(self,name:str,arguments:str|dict)->list|str:
        """
        调用工具
        :param name : str : 工具名称
        :param arguments : str|dict : 工具参数
        :return : list|str : 工具返回结果
        """
        # 获取工具
        if arguments is None:
            arguments = {}
        tool = self.map.get(name)

        if not tool:
            return self._encode_output(
                ToolResult.failure("TOOL_NOT_FOUND", f"工具不存在: {name}")
            )
        try:
            # 解析参数
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except Exception as e:
            return self._encode_output(
                ToolResult.failure("INVALID_ARGUMENTS", str(e))
            )
        if not isinstance(args, dict):
            return self._encode_output(
                ToolResult.failure("INVALID_ARGUMENTS", "工具参数必须是 JSON 对象")
            )

        try:
            # 调用工具方法
            result = tool.function(self.ctx,**args)
        except Exception as e:
            return self._encode_output(
                ToolResult.failure("TOOL_EXECUTION_FAILED", str(e))
            )

        if not isinstance(result, ToolResult):
            # 这是工具实现错误，不允许继续猜测或兼容其他返回格式。
            return self._encode_output(
                ToolResult.failure(
                    "INVALID_TOOL_RESULT",
                    f"工具 {name} 必须返回 ToolResult",
                )
            )

        try:
            return self._encode_output(result)
        except (TypeError, ValueError) as e:
            return self._encode_output(
                ToolResult.failure("INVALID_TOOL_RESULT", str(e))
            )

    @staticmethod
    def _encode_output(result):
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
        res = []
        for name in names:
            module_name = "tools."+name
            module = importlib.import_module(module_name)
            tool = getattr(module,"REGISTER",None)
            if not isinstance(tool, Tool):
                raise TypeError(f"{name}.REGISTER 不是有效的 Tool")
            if tool.schema.get("name") != name:
                raise ValueError(
                    f"工具名称不一致: 配置名={name}, schema名称={tool.schema.get('name')}"
                )
            self.register(tool)
        return self
