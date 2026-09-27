"""协议无关的 LLM 调用入口及三种协议适配。"""

from collections.abc import Generator
import json
from typing import Any

from openai import OpenAI

from head.types import LLMResponse, LLMResponseOutputItem, LLMUsage, validate_protocol


class UnsupportedProtocolError(ValueError):
    """请求协议未被当前 LLM 适配层支持。"""


class LLM:
    """将项目内部请求转换为具体模型协议。"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 system_prompt: str = "", *, protocol: str = "responses") -> None:
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.protocol = validate_protocol(protocol)
        self.base_url = self._normalize_base_url(base_url, self.protocol)
        self.client: OpenAI | None = None
        self.anthropic_client: Any | None = None
        if self.protocol in {"responses", "completions"}:
            self.client = OpenAI(api_key=api_key, base_url=self.base_url)
        else:
            try:
                from anthropic import Anthropic
            except ImportError as error:  # pragma: no cover
                raise RuntimeError("使用 claude 协议需要安装 anthropic 依赖") from error
            kwargs = {"api_key": api_key}
            if base_url:
                kwargs["base_url"] = base_url.rstrip("/")
            self.anthropic_client = Anthropic(**kwargs)

    def call_stream(self, input, tools=None, instructions=None) -> Generator[LLMResponse, Any, None]:
        """按 protocol 分发流式调用。"""
        method = getattr(self, f"call_{self.protocol}_stream")
        return method(input, tools=tools, instructions=instructions)

    def call(self, input, tools=None, instructions=None) -> Any:
        """按 protocol 分发普通调用。"""
        method = getattr(self, f"call_{self.protocol}")
        return method(input, tools=tools, instructions=instructions)

    def call_responses_stream(self, input, tools=None, instructions=None):
        """调用 Responses，并转换为内部流式事件。"""
        with self._openai_client().responses.stream(
            model=self.model, instructions=self._instructions(instructions),
            input=input, tools=tools,
        ) as response:
            has_call = False
            for event in response:
                if not event:
                    continue
                event_type = getattr(event, "type", "")
                if event_type == "response.output_text.delta":
                    yield LLMResponse("text", text=event.delta)
                elif event_type == "response.reasoning_summary_text.done":
                    yield LLMResponse("reasoning_summary", text=event.text)
                elif event_type == "response.reasoning_text.delta":
                    yield LLMResponse("reasoning", text=event.delta)
                elif event_type == "response.output_item.done":
                    item = event.item
                    if getattr(item, "type", None) == "function_call":
                        has_call = True
                        yield LLMResponse(
                            "function_call",
                            arguments=self._parse_arguments(getattr(item, "arguments", None)),
                            name=getattr(item, "name", None),
                            call_id=getattr(item, "call_id", None),
                        )
                elif event_type == "response.completed":
                    usage = getattr(event.response, "usage", None)
                    yield LLMResponse(
                        "done",
                        data=LLMResponseOutputItem.to_LLMResponseOutputItems(
                            getattr(event.response, "output", [])
                        ),
                        is_stop=not has_call,
                        usage=LLMUsage.from_responses_usage(usage),
                    )
                elif event_type == "error":
                    yield LLMResponse("error", message=event)

    def call_responses(self, input, tools=None, instructions=None):
        """调用 Responses；保留 SDK 原始对象兼容旧调用方。"""
        return self._openai_client().responses.create(
            model=self.model, instructions=self._instructions(instructions),
            input=input, tools=tools,
        )

    def call_completions_stream(self, input, tools=None, instructions=None):
        """调用 Chat Completions，并聚合增量 Tool Call 参数。"""
        stream = self._openai_client().chat.completions.create(
            model=self.model,
            messages=self._completions_messages(input, instructions),
            tools=self._completions_tools(tools), stream=True,
        )
        calls = {}
        for chunk in stream:
            choices = getattr(chunk, "choices", []) or []
            if not choices:
                continue
            choice = choices[0]
            delta = getattr(choice, "delta", None)
            text = getattr(delta, "content", None)
            if text:
                yield LLMResponse("text", text=text)
            for tool_call in getattr(delta, "tool_calls", None) or []:
                index = getattr(tool_call, "index", 0) or 0
                current = calls.setdefault(index, {"arguments": ""})
                current["id"] = getattr(tool_call, "id", None) or current.get("id")
                function = getattr(tool_call, "function", None)
                current["name"] = getattr(function, "name", None) or current.get("name")
                current["arguments"] += getattr(function, "arguments", "") or ""
            finish = getattr(choice, "finish_reason", None)
            if finish:
                for call in calls.values():
                    yield LLMResponse("function_call", arguments=self._parse_arguments(call["arguments"]),
                                      name=call.get("name"), call_id=call.get("id"))
                yield LLMResponse("done", data=[LLMResponseOutputItem(
                    type="function_call", id=None, content=None, name=call.get("name"),
                    arguments=call["arguments"], call_id=call.get("id"), status=None,
                ) for call in calls.values()], is_stop=not calls,
                    usage=LLMUsage.from_completions_usage(getattr(chunk, "usage", None)))
                return

    def call_completions(self, input, tools=None, instructions=None):
        """调用 Chat Completions，并返回 SDK 原始响应。"""
        return self._openai_client().chat.completions.create(
            model=self.model, messages=self._completions_messages(input, instructions),
            tools=self._completions_tools(tools),
        )

    def call_claude_stream(self, input, tools=None, instructions=None):
        """调用 Claude Messages，并聚合 tool_use 输入。"""
        stream = self._anthropic_client().messages.stream(
            model=self.model, max_tokens=8192, system=self._instructions(instructions),
            messages=self._claude_messages(input), tools=self._claude_tools(tools),
        )
        active_tool = None
        with stream as events:
            for event in events:
                event_type = getattr(event, "type", "")
                if event_type == "content_block_start":
                    block = getattr(event, "content_block", None)
                    if getattr(block, "type", None) == "tool_use":
                        active_tool = {"id": getattr(block, "id", None), "name": getattr(block, "name", None),
                                       "arguments": dict(getattr(block, "input", None) or {})}
                elif event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if getattr(delta, "type", None) == "text_delta":
                        yield LLMResponse("text", text=delta.text)
                    elif getattr(delta, "type", None) == "input_json_delta" and active_tool:
                        active_tool["raw"] = active_tool.get("raw", "") + getattr(delta, "partial_json", "")
                elif event_type == "content_block_stop" and active_tool:
                    arguments = active_tool.get("arguments") or self._parse_arguments(active_tool.get("raw", ""))
                    yield LLMResponse("function_call", arguments=arguments,
                                      name=active_tool.get("name"), call_id=active_tool.get("id"))
                    active_tool = None
                elif event_type == "message_delta":
                    yield LLMResponse("done", data=[], is_stop=(active_tool is None),
                                      usage=LLMUsage.from_claude_usage(getattr(event, "usage", None)))
                elif event_type == "error":
                    yield LLMResponse("error", message=event)

    def call_claude(self, input, tools=None, instructions=None):
        """调用 Claude Messages，并返回 SDK 原始响应。"""
        return self._anthropic_client().messages.create(
            model=self.model, max_tokens=8192, system=self._instructions(instructions),
            messages=self._claude_messages(input), tools=self._claude_tools(tools),
        )

    def _openai_client(self) -> OpenAI:
        if self.client is None:
            raise UnsupportedProtocolError("当前 LLM 不是 OpenAI 协议")
        return self.client

    def _anthropic_client(self) -> Any:
        if self.anthropic_client is None:
            raise UnsupportedProtocolError("当前 LLM 不是 Claude 协议")
        return self.anthropic_client

    def _instructions(self, instructions):
        return self.system_prompt if instructions is None else instructions

    @staticmethod
    def _normalize_base_url(base_url: str, protocol: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("base_url 必须是非空字符串")
        value = base_url.rstrip("/")
        if protocol in {"responses", "completions"} and not value.endswith("/v1"):
            value += "/v1"
        return value

    @staticmethod
    def _parse_arguments(arguments: Any) -> dict[str, Any]:
        if arguments in (None, ""):
            return {}
        if isinstance(arguments, dict):
            return arguments
        try:
            parsed = json.loads(arguments)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"_raw": str(arguments)}
        return parsed if isinstance(parsed, dict) else {"_raw": parsed}

    @classmethod
    def _completions_messages(cls, input, instructions):
        messages = [{"role": "system", "content": instructions}] if instructions else []
        if isinstance(input, str):
            return messages + [{"role": "user", "content": input}]
        for item in input:
            kind = item.get("type", "message")
            if kind == "function_call":
                messages.append({"role": "assistant", "content": None, "tool_calls": [{
                    "id": item.get("call_id"), "type": "function",
                    "function": {"name": item.get("name"), "arguments": cls._arguments_json(item.get("arguments"))},
                }]})
            elif kind == "function_call_output":
                messages.append({"role": "tool", "tool_call_id": item.get("call_id"),
                                 "content": cls._content_text(item.get("output", item.get("content", "")))})
            else:
                messages.append({"role": item.get("role", "user"),
                                 "content": cls._content_text(item.get("content", ""))})
        return messages

    @staticmethod
    def _completions_tools(tools):
        if tools is None:
            return None
        return [tool if tool.get("type") == "function" and "function" in tool else {
            "type": "function", "function": {
                "name": tool.get("name"), "description": tool.get("description", ""),
                "parameters": tool.get("parameters", tool.get("input_schema", {})),
            }} for tool in tools]

    @classmethod
    def _claude_messages(cls, input):
        if isinstance(input, str):
            return [{"role": "user", "content": input}]
        messages = []
        for item in input:
            kind = item.get("type", "message")
            if kind == "function_call":
                messages.append({"role": "assistant", "content": [{"type": "tool_use", "id": item.get("call_id"),
                    "name": item.get("name"), "input": item.get("arguments", {})}]})
            elif kind == "function_call_output":
                messages.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": item.get("call_id"),
                    "content": cls._content_text(item.get("output", item.get("content", "")))}]})
            elif item.get("role") != "system":
                messages.append({"role": item.get("role", "user"), "content": cls._content_text(item.get("content", ""))})
        return messages

    @staticmethod
    def _claude_tools(tools):
        return [{"name": tool.get("name", tool.get("function", {}).get("name")),
                 "description": tool.get("description", tool.get("function", {}).get("description", "")),
                 "input_schema": tool.get("parameters", tool.get("input_schema", tool.get("function", {}).get("parameters", {})))}
                for tool in (tools or [])]

    @staticmethod
    def _arguments_json(arguments):
        return arguments if isinstance(arguments, str) else json.dumps(arguments or {}, ensure_ascii=False)

    @staticmethod
    def _content_text(content):
        return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
