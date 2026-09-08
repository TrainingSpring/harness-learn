
class ExecutionContext:
    # 工作目录
    workspace:str
    # 代理id
    aid:str
    # 会话id
    sid:str
    # 工具调用最大返回长度
    max_tool_call_length:int = 20000
    def __init__(self,workspace:str,aid:str):
        self.workspace = workspace
        self.aid = aid
