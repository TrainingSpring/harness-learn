import os

from head.llm import LLM
import secrets
import json
from tools.types import Tool

def set_message(role="user", content=""):
    return {"role": role, "content": content}

BASE_URL = "https://token-plan-cn.xiaomimimo.com"
API_KEY = "tp-c7mv9tn67kvmm90hfn48kyoruxkhua9t70zymm8hh43atcvw"
MODEL = "mimo-v2.5"
SYSTEM_PROMPT = "你是一个智能助手，帮助解决问题，实现用户的需求。 "
class AgentLoop:
    def __init__(self):
        self.sid = f"sid_{secrets.token_hex(12)}"
        self.llm = LLM(API_KEY, MODEL, BASE_URL,system_prompt=SYSTEM_PROMPT)
        self.tools = [] # tools列表
        self.tools_map:dict[str,Tool] = {}  # tools映射
        self.message = []
        self.workspace = os.getcwd()


    def register_tool(self, tool:Tool):
        # 注册工具
        schema = tool.schema
        if schema is None:
            raise Exception("Tool schema is required")
        # 添加工具到列表和映射
        if self.tools_map.get(schema["name"]) is None:
            self.tools.append(schema)
            self.tools_map[schema["name"]] = tool

    def register_tools(self,tools:list[Tool]):
        for item in tools:
            name = item.schema["name"]
            if self.tools_map.get(name) is None:
                self.tools.append(item.schema)
                self.tools_map[name] = item
    """
    @description: 调用工具
    @params:
        name: 工具名称
        arguments: 工具参数
    """
    def eval(self, name, arguments=None):
        # 获取工具
        if arguments is None:
            arguments = {}
        tool = self.tools_map.get(name)
        if not tool:
            raise Exception(f"Tool {name} not found")
        try:
            # 解析参数
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except Exception as e:
            raise Exception(f"bad arguments: {e}")

        try:
            # 调用工具方法
            func = tool.function(self,**args)
            return func
        except Exception as e:
            raise Exception(f"tool function error: {e}")

    """
    @description: 运行Agent循环
    @params:
        message: 用户消息
    """
    def run(self,message = None):
        # 添加用户消息
        if message is not None:
            self.message.append({
                "type":"message",
                "role":"user",
                "content":[
                    {
                        "type":"input_text",
                        "text":message
                    }
                ]
            })

        # Agent循环体
        while True:
            # 遍历请求
            for chunk in self.llm.call_responses(self.message, self.tools):
                # 处理请求结果，请求结束后触发
                if chunk.get("type") == "done":
                    data = chunk.get("data")
                    # 处理工具调用结果
                    if chunk.get("is_stop"):
                        # 如果标记了结束，则退出循环体
                        return
                    else:
                        # 处理工具调用结果
                        for item in data:
                            item["role"] = "assistant"
                            # 将大模型处理数据添加进上下文
                            self.message.append(item)
                            # 处理工具调用
                            if item.get("type") == "function_call":
                                # 调用方法名
                                name = item.get("name")
                                # 参数
                                arguments = item.get("arguments")
                                # 调用工具
                                res = self.eval(name, arguments)
                                # 将工具调用结果添加进上下文
                                self.message.append({
                                    "type": "function_call_output",
                                    "name": name,
                                    "output": res,
                                    "call_id":item.get("call_id"),
                                })

                else:
                    yield chunk
