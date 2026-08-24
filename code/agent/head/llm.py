import requests
import json


class LLM:
    def __init__(self, api_key, model, base_url,system_prompt=""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        # self.screen_token = screen_token  # 上下文窗口大小，单位为token
        self.system_prompt = system_prompt  # 系统提示

    """
    @description: Responses调用大模型的能力。 
    @params:
        input: 对话上上下文信息
        tools: 工具列表
    """
    def call_responses_stream(self,input,tools=None):
        # 构建请求的 URL
        url = self.base_url.rstrip("/") + "/v1/responses"

        # 构建请求头和请求体
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "instructions":self.system_prompt,
            "input":input,
            "tools":tools,
            "reasoning": {
                "effort": "high",
                "summary": "detailed"
            },
            "stream":True,
        }
        with requests.post(
                url,
                headers=headers,
                json=body,
                timeout=60,
                stream=True,
        ) as response:
            response.raise_for_status()  # 检查请求状态，若是4xx,5xx自动抛异常
            response.encoding = "utf-8"  # 设置编码为utf-8
            has_call = False  # 标记是否存在函数调用

            # 遍历数据流
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                # 数据会以"data:"开头
                if not line.startswith("data:"):
                    continue
                # 去掉"data:"前缀
                data = line[len("data:"):]
                # 如果数据为"[DONE]"，则表示数据接收完毕
                if data == "[DONE]":
                    break
                # 解析字符串为json
                event = json.loads(data)
                event_type = event.get("type")

                # 处理输出字符串（数据流实时）
                if event_type == "response.output_text.delta":
                    yield {"type": "text", "text": event.get("delta", "")}
                # 处理推理总结完成事件
                if event_type == 'response.reasoning_summary_text.done':
                    yield {"type": "reasoning_summary", "text": event.get("text", "")}
                # 处理推理过程中的文本
                if event_type == "response.reasoning_text.delta":
                    yield {"type": "reasoning", "text": event.get("delta", "")}
                # 处理输出项完成事件, 且为函数调用
                if event_type == "response.output_item.done":
                    item = event.get("item")
                    item_type = item.get("type")
                    if item_type == "function_call":
                        # 标记存在函数调用
                        has_call = True
                        yield {"type": "function_call", "arguments": json.loads(item.get("arguments", "")),
                               "name": item.get("name")}

                # 处理输出完成事件
                if event_type == "response.completed":
                    content = event.get("response").get("output")
                    usage = event.get("response").get("usage")
                    yield {"type": "done", "data": content, "is_stop": not has_call, "usage": usage}
                # 处理错误事件
                elif event_type == "error":
                    yield {"type": "error", "message": event}


    def call_responses(self,input,tools=None):
        url = self.base_url.rstrip("/") + "/v1/responses"

        # 构建请求头和请求体
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        body = {
            "model": self.model,
            "instructions": self.system_prompt,
            "input": input,
            "tools": tools,
            "reasoning": {
                "effort": "high",
                "summary": "detailed"
            },
            "stream": False,
        }
        response = requests.post(
            url,
            headers=headers,
            json=body,
            timeout=60,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.json()
# BASE_URL = "https://token-plan-cn.xiaomimimo.com"
# API_KEY = "tp-c7mv9tn67kvmm90hfn48kyoruxkhua9t70zymm8hh43atcvw"
# MODEL = "mimo-v2.5-pro"
# call_llm = LLM(API_KEY, MODEL, BASE_URL,system_prompt="你是一个智能助手，帮助解决问题，实现用户的需求。 ").call_responses
# for chunk in call_llm("今天的天气如何？ ",tools=tools):
#     if chunk.get("type") == "text" or chunk.get("type") == "reasoning":
#         print(chunk.get("text"), end="", flush=True)
#     if chunk.get("type") == "tool_call":
#         print(chunk.get("name"))
