import os.path

from permission.PermissionManager import PermissionAction, Permission
from runtime.ExecutionContext import ExecutionContext
from tools.types import Tool, ToolResult, handle_path


# 查找唯一文本
def find_unique_text(content:str,text:str):
    first_find = content.find(text)
    if first_find == -1:
        raise Exception(f"'{text}'文本不存在。")
    else:
        second_find = content.find(text, first_find + 1)
        if second_find == -1:
            return {
                "index":first_find,
                "length":len(text)
            }
        else:
            raise Exception(f"'{text}'文本不唯一。")


def edit(ctx:ExecutionContext,target_path:str,edits:list[dict]) -> ToolResult:
    """
     编辑文件内容
    :param  ctx:ExecutionContext - 执行时环境上下文
    :param :target_path:str - 文件路径
    :param :edits:list[dict] - 编辑内容列表
    :returns ToolResult: 编辑结果
    """
    target_path = handle_path(ctx,target_path)
    # 检查目标文件是否存在
    if not os.path.exists(target_path) or not os.path.isfile(target_path):
        return ToolResult.failure(
            "FILE_NOT_FOUND",
            "目标文件不存在。",
            details={"path": target_path},
        )
    # 检查编辑内容是否为空
    if not edits or len(edits) == 0:
        return ToolResult.failure("EMPTY_EDITS", "编辑内容为空。")
    # 读取目标文件内容
    with open(target_path, 'r', encoding='utf-8') as file:
        content = file.read()
    # 检查目标文件内容是否为空
    if not content or len(content) == 0:
        return ToolResult.failure(
            "EMPTY_FILE",
            "目标文件内容为空。",
            details={"path": target_path},
        )
    # 遍历编辑内容
    for item in edits:
        old_str = item.get("old_text") or ""
        new_str = item.get("new_text") or ""
        is_replace_all = item.get("replace_all") or False
        # 检查旧文本是否为空,为空的话则不进行替换
        if old_str:
            try:
                if not is_replace_all and find_unique_text(content, old_str or ""):
                    content = content.replace(old_str, new_str,1)
                else:
                    content = content.replace(old_str, new_str)
            except Exception as e:
                return ToolResult.failure(
                    "EDIT_NOT_APPLICABLE",
                    str(e),
                    details={"path": target_path},
                )

    # 将修改后的内容写回
    with open(target_path, 'w', encoding='utf-8') as file:
        file.write(content)
    return ToolResult.success({
        "operation": "edit_file",
        "path": target_path,
        "edit_count": len(edits),
    })


REGISTER = Tool({
    "type":"function",
    "name": "edit",
    "description": "编辑文本内容",
    "parameters": {
        "type": "object",
        "properties": {
            "target_path": {
                "type": "string",
                "description": "目标文件路径"
            },
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_text": {
                            "type": "string",
                            "description": "旧文本，要求文本唯一性"
                        },
                        "new_text": {
                            "type": "string",
                            "description": "新文本"
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "是否替换所有就文本，默认为False"
                        }
                    }
                },
                "description": "编辑内容列表"
            }
        },
        "required":["target_path","edits"],
        "additionalProperties": False
    }
},edit,Permission(PermissionAction.file_write,"target_path"))
