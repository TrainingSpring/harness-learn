import importlib
import json

from runtime.ExecutionContext import ExecutionContext
from tools.types import Tool, ToolOutput


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
            return "[Error]: Tool not found"
        try:
            # 解析参数
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except Exception as e:
            return "[Error]: " + str(e)

        try:
            # 调用工具方法
            return self._encode_output(tool.function(self.ctx,**args))
        except Exception as e:
            return "[Error]: " + str(e)

    @staticmethod
    def _encode_output(result):
        """将工具业务结果编码为 Responses function_call_output.output。"""
        if isinstance(result, ToolOutput):
            content = list(result.content or [])
            if result.value is not None:
                content.insert(0, {
                    "type": "input_text",
                    "text": Tools._serialize_value(result.value),
                })
            return content
        # 兼容尚未迁移的工具：它们当前已经返回 Responses content 数组。
        if Tools._is_responses_content(result):
            return result
        return Tools._serialize_value(result)

    @staticmethod
    def _serialize_value(value):
        if isinstance(value, str):
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    @staticmethod
    def _is_responses_content(value):
        return (
            isinstance(value, list)
            and all(isinstance(item, dict) and "type" in item for item in value)
            and any(item["type"].startswith("input_") for item in value)
        )

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
