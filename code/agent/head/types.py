from dataclasses import dataclass
from typing import Any


SUPPORTED_PROTOCOLS = frozenset(("responses", "completions", "claude"))


def validate_protocol(protocol: str) -> str:
    """Validate and normalize the protocol used by :class:`LLM`."""
    if not isinstance(protocol, str) or not protocol.strip():
        raise ValueError("protocol 必须是非空字符串")
    normalized = protocol.strip().lower()
    if normalized not in SUPPORTED_PROTOCOLS:
        supported = ", ".join(sorted(SUPPORTED_PROTOCOLS))
        raise ValueError(f"不支持的 LLM 协议: {protocol}，支持: {supported}")
    return normalized

class LLMUsage:
    """LLMUsage
    Usage数据结构
    """
    total_tokens: int
    cached_token: int
    output_tokens: int
    input_tokens: int
    def __init__(self,total_tokens,cached_token,output_tokens,input_tokens):
        self.total_tokens = total_tokens
        self.cached_token = cached_token
        self.output_tokens = output_tokens
        self.input_tokens = input_tokens

    @staticmethod
    def from_responses_usage(usage: Any):
        return LLMUsage(
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            cached_token=getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
        )

    @staticmethod
    def from_completions_usage(usage: Any):
        return LLMUsage(
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
            cached_token=0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        )

    @staticmethod
    def from_claude_usage(usage: Any):
        input_tokens = getattr(usage, "input_tokens", 0) or 0
        output_tokens = getattr(usage, "output_tokens", 0) or 0
        return LLMUsage(
            total_tokens=input_tokens + output_tokens,
            cached_token=getattr(usage, "cache_read_input_tokens", 0) or 0,
            output_tokens=output_tokens,
            input_tokens=input_tokens,
        )

    to_LLMUsage = from_responses_usage


class LLMResponseOutputItem:
    type:str
    id:str
    content: str|list|None
    name:str|None
    arguments:str|None
    call_id:str|None
    status:str|None
    raw:dict[str, Any]|None

    def __init__(self,type,id,content,name,arguments,call_id,status,raw=None):
        self.type = type
        self.id = id
        self.content = content
        self.name = name
        self.arguments = arguments
        self.call_id = call_id
        self.status = status
        self.raw = raw

    @staticmethod
    def to_LLMResponseOutputItem(item: Any):
        return LLMResponseOutputItem(
            type=item.type,
            id=getattr(item,"id",None),
            content=getattr(item,"content",None),
            name=getattr(item,"name",None),
            arguments=getattr(item,"arguments",None),
            call_id=getattr(item,"call_id",None),
            status=getattr(item,"status",None),
            raw=LLMResponseOutputItem._raw_item(item),
        )

    @staticmethod
    def _raw_item(item: Any) -> dict[str, Any] | None:
        """保留 SDK 输出项的完整字段，供协议连续性状态在下一轮回放。"""
        if isinstance(item, dict):
            return dict(item)
        dump = getattr(item, "model_dump", None)
        if callable(dump):
            value = dump(exclude_none=True)
            return value if isinstance(value, dict) else None
        return None
    @staticmethod
    def to_LLMResponseOutputItems(items: list[Any]):
        return [LLMResponseOutputItem.to_LLMResponseOutputItem(item) for item in items]

    def to_dict(self):
        """
        将LLMResponseOutputItem转换为字典，方便后续处理
        """
        res = {
            "type": self.type,
        }
        if self.id is not None:
            res["id"] = self.id
        if self.content is not None:
            res["content"] = self.content
        if self.name is not None:
            res["name"] = self.name
        if self.arguments is not None:
            res["arguments"] = self.arguments
        if self.call_id is not None:
            res["call_id"] = self.call_id
        if self.status is not None:
            res["status"] = self.status
        return res


@dataclass
class LLMResponse:
    type: str
    text: str|None = None
    data: list[LLMResponseOutputItem]|None = None
    is_stop: bool|None = None
    arguments:str|None = None
    name:str|None = None
    call_id: str|None = None
    usage:LLMUsage|None=None
    message:Any|None = None


@dataclass
class LLMConfig:
    """
    LLM配置数据结构
    :param base_url: str: OpenAI API的baseUrl
    :param api_key: str: OpenAI API的密钥
    :param model:str: 使用的模型名
    """
    base_url:str
    api_key:str
    model:str
    protocol: str = "responses"

    def __post_init__(self) -> None:
        self.protocol = validate_protocol(self.protocol)
