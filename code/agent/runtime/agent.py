import secrets

from head.llm import LLM
from head.types import LLMConfig
from runtime.runtime import Runtime
from tools.tools import Tools
from context.context import Context


class Agent:
    def __init__(self,llm_config:LLMConfig,tools:list[str],context:Context|None=None,aid:str=""):
        self.llm = LLM(llm_config.base_url,llm_config.api_key,llm_config.model,llm_config.instructions)
        self.tools = Tools()
        self.tools.register_by_names(tools)
        self.aid = f"agent_{secrets.token_hex(10)}" if not aid else aid
        self.context = context if context is not None else Context(LLM(llm_config.base_url,llm_config.api_key,llm_config.model,llm_config.instructions))
        self.runtime = Runtime(self.llm,self.tools,self.context)

    def send(self,message:str):
        return self.runtime.run(message)

