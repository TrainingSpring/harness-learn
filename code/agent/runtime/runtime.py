from context.context import Context
from head.llm import LLM
from tools.tools import Tools


class Runtime:
    def __init__(self,llm:LLM,tools:Tools,context:Context):
        self.llm = llm
        self.tools = tools
        self.context = context
