import datetime
from tools.types import Tool


def get_weather(date:str=datetime.date.today().strftime("%Y-%m-%d")):
    return {
        "date": date,
        "weather": "sunny",
        "temperature": "25℃"
    }

GET_WEATHER_REGISTER = Tool(function=get_weather,schema={
        "type":"function",
        "name":"get_weather",
        "description":"Get weather information for a specific date",
        "parameters":{
            "type":"object",
            "properties":{
                "date":{
                    "type":"string",
                    "description":"日期，格式为YYYY-MM-DD，可不填，默认为当天"
                }
            },
            "required":[],
            "additionalProperties": False
        }
    })