import locale

from loop.loop import AgentLoop
import subprocess
import os

from tools.types import Tool


"""
@description: 解码输出 , 为啥要自己解码： 因为自动解码的话会出现硬解码不同导致乱码的问题
@param data: bytes

"""
def decode_output(data: bytes | None) -> str:
    if not data:
        return ""

    # 获取当前系统偏好的文本编码
    preferred_encoding = locale.getpreferredencoding(False)

    encodings = [
        "utf-8-sig",          # 支持带 BOM 的 UTF-8
        "utf-8",              # Node、Git、Python 等经常使用
        preferred_encoding,   # 中文 Windows 通常是 cp936
        "gb18030",            # 比 GBK 覆盖范围更大
    ]

    # 尝试使用不同的编码解码数据
    for encoding in encodings:
        try:
            return data.decode(encoding)[-20000:]
        except (UnicodeDecodeError, LookupError):
            continue

    return data.decode("utf-8", errors="replace")

def bash(self:AgentLoop,command:str,timeout:int|None = None):

    if os.name == "nt":
        # command = ["powershell.exe","-NoProfile","-NonInteractive", "-Command", command]
        command = "powershell.exe"+" -NoProfile"+" -NonInteractive"+ " -Command " +  command
    else:
        command = [
            "bash",
            "-lc",
            command,
        ]
    result = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=self.workspace
    )
    if result.returncode == 0:
        return {
            "type": "text",
            "text": decode_output(result.stdout),
            "status":"ok"
        }
    else:
        return {
            "type": "text",
            "text": decode_output(result.stderr),
            "status":"error"
        }

# agent = AgentLoop()
# res = bash(agent,"netstat -ano",10)
REGISTER = Tool({
        "type":"function",
        "name":"bash",
        "description":"执行bash命令,windows系统中是powershell",
        "parameters":{
            "type":"object",
            "properties":{
                "command": {
                    "type": "string",
                    "description": "要执行的bash命令"
                },
                "timeout": {
                    "type": "number",
                    "description": "命令执行超时时间,单位秒 ， 不填则默认不设超时时间"
                }
            },
            "required":["command"],
            "additionalProperties": False
        }
    },bash)