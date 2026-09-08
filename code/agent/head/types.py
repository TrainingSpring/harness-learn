from openai.types.responses.response import Response,ResponseUsage,ResponseOutputItem
from dataclasses import dataclass
from typing import Any

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
    def to_LLMUsage(usage:ResponseUsage):
        return LLMUsage(
            total_tokens=usage.total_tokens,
            cached_token=usage.input_tokens_details.cached_tokens,
            output_tokens=usage.output_tokens,
            input_tokens=usage.input_tokens,
        )


class LLMResponseOutputItem:
    type:str
    id:str
    content: str|list|None
    name:str|None
    arguments:str|None
    call_id:str|None
    status:str|None
    def __init__(self,type,id,content,name,arguments,call_id,status):
        self.type = type
        self.id = id
        self.content = content
        self.name = name
        self.arguments = arguments
        self.call_id = call_id
        self.status = status

    @staticmethod
    def to_LLMResponseOutputItem(item:ResponseOutputItem):
        return LLMResponseOutputItem(
            type=item.type,
            id=getattr(item,"id",None),
            content=getattr(item,"content",None),
            name=getattr(item,"name",None),
            arguments=getattr(item,"arguments",None),
            call_id=getattr(item,"call_id",None),
            status=getattr(item,"status",None),
        )
    @staticmethod
    def to_LLMResponseOutputItems(items:list[ResponseOutputItem]):
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
    usage:LLMUsage|None=None
    message:Any|None = None


@dataclass
class LLMConfig:
    """
    LLM配置数据结构
    :param base_url: str: OpenAI API的baseUrl
    :param api_key: str: OpenAI API的密钥
    :param instructions:str: LLM的指令
    :param model:str: 使用的模型名
    """
    base_url:str
    api_key:str
    model:str
    instructions:str