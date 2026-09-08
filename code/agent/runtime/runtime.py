import os

from context.context import Context
from head.llm import LLM, LLMResponseOutputItem
from runtime.ExecutionContext import ExecutionContext
from tools.tools import Tools


class Runtime:
    def __init__(self,llm:LLM,tools:Tools,context:Context,ctx:ExecutionContext):
        self.llm = llm
        self.tools = tools
        self.context = context
        self.ctx = ctx  # 运行时上下文（Agent运行时的参数）
        self.sys_message = [
            {
                "type": "message",
                "role": "developer",
                "content": [
                    {
                        "type": "input_text",
                        "text": f"当前系统环境：{'windows' if os.name == 'nt' else 'linux'},工作目录{ctx.workspace}"
                    }
                ]
            }
        ]

    def call_llm(self):
        return self.llm.call_responses_stream(self.context.get_msg(self.sys_message),self.tools.list)

    def run(self,message:str):
        """
        运行函数,包含loop
        """
        self.context.append_msg(message)
        while True:
            for res in self.call_llm():
                if res.type == "done":
                    data = res.data or []
                    for item in data:
                        if item.type == "message":
                            self.context.append_msg(item)
                        elif item.type == "function_call":
                            self.context.append_msg(item)
                            response = self.tools.eval(item.name,item.arguments)
                            self.context.append_msg({
                                "type": "function_call_output",
                                "output": response,
                                "call_id":item.call_id,
                            })
                    if res.is_stop:
                        yield res
                        return res
                else:
                    yield res