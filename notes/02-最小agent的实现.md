# 最小agent的实现

> 我想既然要从头学起， 第一步应该是怎么调用大模型。 
> 网上找了很多相关参考资料 ， 都是先实现一个Agent Loop ， 然后实现一些虚拟的tools ， mock一些数据，先跑通agent循环， 再做大模型接入
> 我不太喜欢这个顺序，所以我打算从大模型的接入开始了解。
> 代码以python为主。

## 大模型的接入

大模型的接入有多种形式， 一个是SDK的方式， 比如Anthropic ， OpenAI， 在python中都有对应的包, 通过引入的方式来调用。 如下

``` pyton
from openai import OpenAI

from anthropic import Anthropic

```


虽然大多数模型都兼容了OpenAI的格式， 但我认为既然是学习， 应当学原理， 在应用的时候更加得心应手， 所以我选择直接发送http请求。 后续再用SDK。

### OpenAI请求体
> OpenAI请求体有两种模式
> composition  一个比较通用的请求体格式
> responses    OpenAI新的请求格式
> 我们先以Responses格式为主


#### Responses 请求格式

本来是看的官方文档，但是感觉官方文档写的示例太基础，不太符合实际场景，然后直接抓了个codex数据包，来分析codex的请求体。 

总体请求格式如下：

```javascript
let input = {
    "model": "gpt-5.6-sol",  // 指定模型
    "instructions": "You are Codex, an agent based on GPT-5. You and the user share one workspace, and your job ...", // 系统提示词
    "input":[           // 输入内容（全部都在这儿）
        {
            "type": "message",
            "id": "msg_019fe636-a832-7340-b9cf-aba88c0f6230",
            "role": "user",
            "content": [{
                "type": "input_text",
                "text": "用户消息.."
            }]
        },
        {
		"type": "reasoning",
		"id": "rs_0915acba748d5343016a785fed1528819880b1c8a8d19b9e72",
		"summary": [{
			"type": "summary_text",
			"text": "**Preparing complete pseudocode with imports**"
		}, {
			"type": "summary_text",
			"text": "**Crafting minimal urllib.request example with imports**"
		}],
		"content": null,
		"encrypted_content": "gAAAAABqeF_x5bRPVycCY_KvLqr..."
	}, {
		"type": "message",
		"id": "msg_0915acba748d5343016a785ff1a6548198a3c1b1e4ff3b5025",
		"role": "assistant",
		"content": [{
			"type": "output_text",
			"text": "回复消息..."
		}],
		"phase": "final_answer"
	}
    ],
    "tools":[           // 可调用的工具
        {
		"type": "function", // 类型
		"name": "shell_command",// 名称
		"description": "Runs a Powershell command (Windows) and returns its output.\n\nExamples of valid command strings:...", // 描述
		"strict": false, // 严格模式
		"parameters": { // 参数定义
			"type": "object", // 类型
			"properties": { // 参数属性
				"command": {
					"type": "string",
					"description": "Shell script to run in the user's default shell."
				},
				"justification": {
					"type": "string",
					"description": "User-facing approval question for `require_escalated`; omit otherwise."
				},
				"login": {
					"type": "boolean",
					"description": "True runs with login shell semantics; false disables them. Defaults to true."
				},
				"prefix_rule": {
					"type": "array",
					"description": "Reusable approval prefix for `cmd`, only with `sandbox_permissions: \"require_escalated\"`; for example [\"git\", \"pull\"].",
					"items": {
						"type": "string"
					}
				},
				"sandbox_permissions": {
					"type": "string",
					"description": "Per-command sandbox override. Defaults to `use_default`; use `require_escalated` for unsandboxed execution.",
					"enum": ["use_default", "require_escalated"]
				},
				"timeout_ms": {
					"type": "number",
					"description": "Maximum command runtime. Defaults to 10000 ms."
				},
				"workdir": {
					"type": "string",
					"description": "Working directory for the command. Defaults to the turn cwd."
				}
			},
			"required": ["command"], // 必填参数
			"additionalProperties": false  // 额外属性， 意思是是否允许出现没有定义的参数字段
		}
	}
    ],
    "reasoning": {
		"effort": "high",   // 推理强度
		"summary": "detailed" // 摘要类型
	},
    "stream":true, // 是否是流式输出
}

```

看着很大一坨，比较复杂的就是input和tools
input中传递的是上下文和消息， 根据官方文档， 你甚至可以直接给input传递字符串
tools 可用的工具， agent在执行任务的时候，可能会用到工具，从这里面选， description就是用来描述工具用途的

##### instructions 字段

也就是系统提示词，用来定义智能体

##### input字段 
> input 字段可以是数组，也可以是一个字符串， 如果是一个字符串，则没有上下文，也就是一次性的会话，在agent中用不到。 
> 以下是字段基本描述

- type， 输入类型 一般有： `message`,`reasoning`,`web_search_call`,`function_call`
  - message 常规的消息， 包括用户消息和大模型的回复消息
  - reasoning  来自模型的思考消息
  - web_search_call  模型调用网页搜索
  - function_call 模型调用tools中的函数
不难看出， 其实这些类型来说， 只有message对我们是有效的

- id 很好理解， 这条消息的id
- role ， 这条消息的所属角色， 目前我所知道的就四种角色
  - user  用户消息
  - assistant 来自大模型的消息
  - developer  开发者的消息， 这个一般定义开发者的规则，替代system 角色（codex告诉我的）
  - system  基本被`developer`和`instructions`参数替代了
- content  消息内容， 消息内容是一个数组,或者null 数组中包含多个对象，对象参数如下：
  - type ， 定义消息的类型
    - input_text   消息文本
    - input_image   图片
    - input_file    文件
  - text 是input_text专有的
  - image_url： input_image专用 可以用网络url 也可以用base64                       （codex告诉我的） 因为抓的数据包里暂时没有这类信息。 
  - file_url：  input_file 专用， 外部文件的url    .                              （codex告诉我的） 因为抓的数据包里暂时没有这类信息。 
  - file_data： input_file 专用， base64文件                                      （codex告诉我的） 因为抓的数据包里暂时没有这类信息。 
  - file_id  ： input_file和input_image都可用，目前我还不知道咋用。                （codex告诉我的） 因为抓的数据包里暂时没有这类信息。 

### LLM调用代码示例

由于本项目只是作为Agent 的示例，所以只实现了一个LLM的调用，实际应用中，需要根据具体需求，实现不同的LLM调用。或者编写一个适配器，用于适配市面上常见的大模型。

```python
import requests
import json


class LLM:
    def __init__(self, api_key, model, base_url,screen_token=256,system_prompt=""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.screen_token = screen_token  # 上下文窗口大小，单位为token
        self.system_prompt = system_prompt  # 系统提示

    """
    @description: Responses调用大模型的能力。 
    @params:
        input: 对话上上下文信息
        tools: 工具列表
    """
    def call_responses(self,input,tools=None):
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
            "max_completion_tokens": self.screen_token,
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
            response.raise_for_status() # 检查请求状态，若是4xx,5xx自动抛异常
            response.encoding = "utf-8"  # 设置编码为utf-8
            has_call = False # 标记是否存在函数调用

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
                    yield {"type":"text","text":event.get("delta", "")}
                # 处理推理总结完成事件
                if event_type == 'response.reasoning_summary_text.done':
                    yield {"type":"reasoning_summary","text":event.get("text","")}
                # 处理推理过程中的文本
                if event_type == "response.reasoning_text.delta":
                    yield {"type":"reasoning","text":event.get("delta", "")}
                # 处理输出项完成事件, 且为函数调用
                if event_type == "response.output_item.done":
                    item = event.get("item")
                    item_type = item.get("type")
                    if item_type == "function_call":
                        # 标记存在函数调用
                        has_call = True
                        yield {"type":"function_call","arguments":json.loads(item.get("arguments","")), "name":item.get("name")}

                # 处理输出完成事件
                if event_type == "response.completed":
                    content = event.get("response").get("output")
                    yield {"type":"done","data":content,"is_stop":has_call}
                # 处理错误事件
                elif event_type == "error":
                    yield {"type":"error","message":event}
```

## 核心Agent Loop的实现。 
本质就是，将用户信息和可调用的工具列表发给大模型， 大模型根据用户需求来推理是否需要调用工具， 默认没有调用tool的时候，意味着停止本次loop， 否则调用tool，并将tool结果返回给大模型。 


Agent Loop核心代码的实现
```python
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
```