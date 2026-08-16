from loop.loop import AgentLoop
import os
from tools.types import Tool

"""
@description: 写文件
@param self: AgentLoop
@param target_path: 文件路径
@param content: 文件内容

"""
def write(self:AgentLoop,target_path:str,content:str=""):
    cur_path = target_path
    # 判定是否是相对路径
    if not os.path.isabs(target_path):
        if target_path.startswith("/"):
            target_path = target_path[1:]
        cur_path = os.path.join(self.workspace, target_path)
    # 如果目录路径不存在，创建目录
    try:
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
    except Exception as e:
        return {
            "status":"error",
            "type":"make_dir",
            "path":target_path,
            "error":str(e)
        }

    # 判定路径是文件路径还是目录路径
    if not cur_path.endswith("/"):
        try:
            with open(target_path, 'w', encoding='utf-8') as file:
                file.write(content)
            return {
                "status": "ok",
                "type": "write_file",
                "path": target_path,
                "size": len(content)
            }
        except Exception as e:
            return {
                "status": "error",
                "type": "write_file",
                "path": target_path,
                "error": str(e)
            }
    else:
        return {
            "status":"ok",
            "type":"make_dir",
            "path":target_path
        }


REGISTER = Tool(
    {
        "type": "function",
        "name": "write",
        "description": "写文件或者创建文件夹，如果target_path传递文件夹路径，则创建文件夹，传递文件路径则创建/覆盖文件，如果传递的路径中的目录不存在，则会创建目录。",
        "parameters": {
            "type": "object",
            "properties": {
                "target_path": {
                    "type": "string",
                    "description": "相对路径或者绝对路径，推荐使用相对路径。相对路径不要以斜杠开头，目录以斜杠结尾 "
                },
                "content": {
                    "type": "string",
                    "description": "要写入的内容，如果传递文件路径则忽略此参数"
                },
            },
            "required": ["target_path"],
            "additionalProperties": False
        }
    },write
)