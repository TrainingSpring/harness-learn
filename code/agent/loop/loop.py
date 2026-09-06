import os

from head.llm import LLM
import secrets
import json
from tools.types import Tool
from collections import deque


def set_message(role="user", type:str="message",content=""):
    return {"role": role, "content": content,"type":type}

BASE_URL = "http://192.168.31.6:18080"
API_KEY = "sk-5c206cdd7da2521f5949d6f78f9f40d1320caf8414eb187423c0e23e0619c8a8"
MODEL = "gpt-5.6-luna"
SYSTEM_PROMPT = "你是一个智能助手，帮助解决问题，实现用户的需求。 "


def rough_tokens(text: str) -> int:
    """粗略计算文本的 token 数"""
    chinese = sum("\u4e00" <= ch <= "\u9fff" for ch in text)
    other = len(text) - chinese

    return int(chinese * 1.5 + other / 4)


class AgentLoop:
    def __init__(self):
        self.sid = f"sid_{secrets.token_hex(12)}"
        self.max_context_tokens = 256*1024  # 上下文窗口大小
        self.llm = LLM(BASE_URL,API_KEY, MODEL, system_prompt=SYSTEM_PROMPT)
        self.tools = [] # tools列表
        self.tools_map:dict[str,Tool] = {}  # tools映射
        self.workspace = os.getcwd()
        # 系统消息
        self.sys_message = [
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"当前系统环境：{'windows' if os.name == 'nt' else 'linux'},工作目录{self.workspace}"
                    }
                ]
            }
        ]
        # agent 消息
        self.message =[]
        # 用量信息
        self.usage = {}
        self.used_tokens = 0   # 已使用的token数
        self.call_result_num = 5  # 调用工具结果集的保留数量

    """
    @description: 处理上下文,主要是合并系统消息和用户及LLM消息
    @params:
        messages: 要新增的用户消息
    """

    def context_handel(self, messages = None):
        # 合并系统消息和agent消息
        if messages:
            self.append_message(messages)
        self.check_points()
        return self.sys_message + self.message


    def append_message(self, message):
        self.message.append(message)
        return self.message

    """
    @description: 调用管理，用于优化处理位于上下文中的工具调用结果
    """
    def call_manage(self):
        msg = self.message
        ignore_num = 0
        for i in reversed(range(len(msg) - 1)):
            item = msg[i]
            name = item.get("name")
            if item.get("type") == "function_call" and ignore_num < self.call_result_num:
                ignore_num += 1
            if ignore_num > self.call_result_num:
                if item.get("type") == "function_call":
                    self.message[i] = set_message(role="assistant", content=json.dumps({
                        "tool": name,
                        "kind": "history_tool_call",
                        "bytes_written": len(item.get("arguments")),
                        "message": f"{name}的历史调参数内容已被移除。",
                    }))
                elif item.get("type") == "function_call_output":
                    item["output"] = f"工具调用结果内容已从上下文移除，请重新调用{item.get('name')}"



    def check_points(self):
        """
        @description: 检测点，进行上下文治理，用于处理上下文过大的问题。
        """
        rate = self.used_tokens / self.max_context_tokens
        if 0.6 < rate < 0.7:
            self.call_manage()
        elif rate >= 0.7:
            self.compact_context()
            pass

        return self.message



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
            return {"status":"error","message":"Tool not found"}
        try:
            # 解析参数
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except Exception as e:
            return {
                "status":"error",
                "message":str(e)
            }

        try:
            # 调用工具方法
            func = tool.function(self,**args)
            return func
        except Exception as e:
            return {
                "status":"error",
                "message":str(e)
            }

    """
    @description: 运行Agent循环
    @params:
        message: 用户消息
    """
    def run(self,message = None):
        # 添加用户消息
        if message is not None:
            self.append_message({
                "type":"message",
                "role":"user",
                "content":[
                    {
                        "type":"input_text",
                        "text":message
                    }
                ]
            })
        else:
            return None

        # Agent循环体
        while True:
            # 遍历请求
            for chunk in self.llm.call_responses_stream(self.context_handel(), self.tools):
                # 处理请求结果，请求结束后触发
                if chunk.type == "done":
                    data = chunk.data or []
                    self.usage = chunk.usage
                    self.used_tokens = chunk.usage.total_tokens
                    cached_token = self.usage.input_tokens_details.cached_tokens
                    input_tokens = self.usage.input_tokens
                    output_tokens = self.usage.output_tokens
                    total_tokens = self.usage.total_tokens

                    # 处理工具调用结果
                    # 处理工具调用结果
                    for item in data:
                        item.role = "assistant"
                        # 处理工具调用
                        if item.type == "message":
                            # 将大模型处理数据添加进上下文
                            self.append_message(item)
                        elif item.type == "function_call":
                            # 调用方法名
                            name = item.name
                            # 参数
                            arguments = item.arguments

                            call_id = item.call_id
                            self.append_message({
                                "type": "function_call",
                                "id": item.id,
                                "name": name,
                                "arguments": arguments,
                                "call_id": call_id,
                            })
                            # 调用工具
                            res = self.eval(name, arguments)
                            # 将工具调用结果添加进上下文
                            self.append_message({
                                "type": "function_call_output",
                                # "name": name,
                                "output": res,
                                "call_id":call_id,
                            })

                    if chunk.is_stop:
                        yield chunk
                        return chunk

                else:
                    yield chunk
