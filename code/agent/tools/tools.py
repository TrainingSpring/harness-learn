import json

from types import Tool


class Tools:
    """
    工具集
    """
    def __init__(self):
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
            return tool.function(self,**args)
        except Exception as e:
            return "[Error]: " + str(e)
