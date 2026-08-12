from tools.types import Tool

def get_location():
    return {"location":"四川省达州市通川区"}


GET_LOCATION_REGISTER = Tool({
        "type":"function",
        "name":"get_location",
        "description":"Get location information",
    },get_location)