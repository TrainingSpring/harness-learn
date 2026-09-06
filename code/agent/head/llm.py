from typing import Any, Generator

import requests
import json
from openai import OpenAI,types
from openai.types.responses.response import Response,ResponseUsage,ResponseOutputItem

from dataclasses import dataclass
@dataclass
class LLMResponse:
    type: str
    text: str|None = None
    data: list[ResponseOutputItem]|None = None
    is_stop: bool|None = None
    arguments:str|None = None
    name:str|None = None
    usage:ResponseUsage|None=None
    message:Any|None = None

class LLM:
    def __init__(self, base_url, api_key, model,system_prompt=""):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt  # 系统提示
        if base_url[-3:] != "/v1":
            base_url += "/v1"

        self.base_url = base_url
        self.client = OpenAI(api_key=api_key,base_url =base_url)


    """
    @description: Responses调用大模型的能力。 
    @params:
        input: 对话上上下文信息
        tools: 工具列表
    """
    def call_responses_stream(self,input,tools=None)-> Generator[LLMResponse, Any, None]:
        with self.client.responses.stream(
            model=self.model,
            instructions=self.system_prompt,
            input=input,
            tools=tools,
        ) as response:
            has_call = False  # 标记是否存在函数调用
            # 遍历数据流
            for event  in response:
                if not event:
                    continue

                # 如果数据为"[DONE]"，则表示数据接收完毕
                # if data == "[DONE]":
                #     break
                # # 解析字符串为json
                # event = json.loads(data)
                event_type = event.type
                # 处理输出字符串（数据流实时）
                if event_type == "response.output_text.delta":
                    yield LLMResponse("text",event.delta)
                # 处理推理总结完成事件
                if event_type == 'response.reasoning_summary_text.done':
                    yield LLMResponse("reasoning_summary",event.text)
                # 处理推理过程中的文本
                if event_type == "response.reasoning_text.delta":
                    yield LLMResponse("reasoning",event.delta)
                # 处理输出项完成事件, 且为函数调用
                if event_type == "response.output_item.done":
                    item = event.item
                    item_type = item.type
                    if item_type == "function_call":
                        # 标记存在函数调用
                        has_call = True
                        yield LLMResponse("function_call",arguments=json.loads(item.arguments),name=item.name)

                # 处理输出完成事件
                if event_type == "response.completed":
                    content = event.response.output
                    usage = event.response.usage
                    yield LLMResponse("done",data=content,is_stop=not has_call,usage=usage)
                # 处理错误事件
                elif event_type == "error":
                    yield LLMResponse("error",message=event)


    def call_responses(self,input,tools=None):
        response = self.client.responses.create(
            model=self.model,
            instructions=self.system_prompt,
            input=input,
            tools=tools,
        )
        return response
# BASE_URL = "https://token-plan-cn.xiaomimimo.com"
# API_KEY = "tp-c7mv9tn67kvmm90hfn48kyoruxkhua9t70zymm8hh43atcvw"
# MODEL = "mimo-v2.5-pro"
# call_llm = LLM(API_KEY, MODEL, BASE_URL,system_prompt="你是一个智能助手，帮助解决问题，实现用户的需求。 ").call_responses
# for chunk in call_llm("今天的天气如何？ ",tools=tools):
#     if chunk.get("type") == "text" or chunk.get("type") == "reasoning":
#         print(chunk.get("text"), end="", flush=True)
#     if chunk.get("type") == "tool_call":
#         print(chunk.get("name"))
