import os
import secrets

from head.llm import LLM
from head.types import LLMConfig
from runtime.runtime import Runtime
from tools.tools import Tools
from context.context import Context
from runtime.ExecutionContext import ExecutionContext

class Agent:
    def __init__(self,llm_config:LLMConfig,tools:list[str],context:Context|None=None,aid:str=""):
        self.aid = f"agent_{secrets.token_hex(10)}" if not aid else aid
        # 工作目录
        self.workspace = os.getcwd()
        # 执行上下文
        self.ctx = ExecutionContext(self.workspace, self.aid)
        # LLM
        self.llm = LLM(llm_config.base_url,llm_config.api_key,llm_config.model,llm_config.instructions)
        # 工具
        self.tools = Tools(self.ctx)
        # 注册工具

        self.tools.register_by_names(tools)
        # 上下文
        self.context = context if context is not None else Context(LLM(llm_config.base_url,llm_config.api_key,llm_config.model,llm_config.instructions),self.ctx)
        # 运行时（loop）
        self.runtime = Runtime(self.llm,self.tools,self.context,self.ctx)


    def send(self,message:str):
        return self.runtime.run(message)

