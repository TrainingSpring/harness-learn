from loop.loop import AgentLoop
from tools.types import Tool

def get_location(self:AgentLoop):
    print(self.work_dir)
    return {"location":"四川省达州市通川区"}


GET_LOCATION_REGISTER = Tool({
        "type":"function",
        "name":"get_location",
        "description":"Get location information",
    },get_location)