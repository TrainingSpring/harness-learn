from loop.loop import AgentLoop
from tools import get_weather,get_location

agent = AgentLoop()

agent.register_tool(get_weather.GET_WEATHER_REGISTER)

agent.register_tools([
    get_location.GET_LOCATION_REGISTER,
    get_weather.GET_WEATHER_REGISTER
])

res = agent.run("今天天气如何")

for item in res:
    print(item)
