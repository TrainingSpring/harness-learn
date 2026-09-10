import os

from permission.types import PermissionAction, PermissionRequirement
from runtime.ExecutionContext import ExecutionContext
from tools.types import Tool, ToolResult, handle_path

"""
@description: 写文件
@param ctx: ExecutionContext
@param target_path: 文件路径
@param content: 文件内容
@return ToolResult: 写入结果

"""
def write(ctx:ExecutionContext,target_path:str,content:str="") -> ToolResult:
    # 判定是否是相对路径
    cur_path = target_path = handle_path(ctx,target_path)
    # 如果目录路径不存在，创建目录
    try:
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
    except Exception as e:
        return ToolResult.failure(
            "CREATE_DIRECTORY_FAILED",
            str(e),
            details={"path": target_path},
        )

    # 判定路径是文件路径还是目录路径
    if not cur_path.endswith("/"):
        try:
            with open(target_path, 'w', encoding='utf-8') as file:
                file.write(content)
            return ToolResult.success({
                "operation": "write_file",
                "path": target_path,
                "size": len(content),
            })
        except Exception as e:
            return ToolResult.failure(
                "WRITE_FILE_FAILED",
                str(e),
                details={"path": target_path},
            )
    else:
        return ToolResult.success({
            "operation": "make_directory",
            "path": target_path,
        })


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
    },write,PermissionRequirement(PermissionAction.FILE_WRITE,"target_path"))
