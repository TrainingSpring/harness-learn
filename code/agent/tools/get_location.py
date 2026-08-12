from tools.types import Tool

def get_location():
    return {"location":"中国四川省成都市青白江区"}


GET_LOCATION_REGISTER = Tool({
        "type":"function",
        "name":"get_location",
        "description":"Get location information",
    },get_location)