import os.path
import base64
import mimetypes

from runtime.ExecutionContext import ExecutionContext
from tools.types import ImageAttachment, Tool, ToolResult, handle_path

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".bmp"
}

def is_img(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS
"""
@description: 读取目标路径的文件或者文件夹中的内容。 
@param target_path: 目标路径 ， 可以是相对路径和绝对路径，也可以是目录路径
@param offset: 读取偏移量
@param limit: 读取的最大字符数
@return ToolResult: 读取结果；图片通过 attachments 返回
"""
def read(ctx:ExecutionContext, target_path:str, offset=0, limit=5000) -> ToolResult:
    cur_path = handle_path(ctx,target_path)
    limit = min(limit,ctx.max_tool_call_length)
    # 判定是否是相对路径

    # 判定路径是文件路径还是目录路径
    if os.path.isfile(cur_path):
        if not os.path.exists(cur_path):
            return ToolResult.failure(
                "PATH_NOT_FOUND",
                "目标路径不存在",
                details={"path": cur_path},
            )

        if is_img(cur_path):
            mime_type, _ = mimetypes.guess_type(cur_path)
            if mime_type is not None:
                image_types = None;
                with open(cur_path, 'rb') as file:
                    image_types = file.read()
                image_base64 = base64.b64encode(image_types).decode("ascii")
                return ToolResult.success(
                    data={
                        "type": "image",
                        "path": cur_path,
                        "mime_type": mime_type,
                    },
                    attachments=[
                        ImageAttachment(
                            url=f"data:{mime_type};base64,{image_base64}",
                            mime_type=mime_type,
                        )
                    ],
                )
            return ToolResult.failure(
                "UNKNOWN_IMAGE_FORMAT",
                "图片格式未知!",
                details={"path": cur_path},
            )
        with open(cur_path, 'r', encoding='utf-8') as f:
            f.seek(offset)
            content = f.read(limit)
            return ToolResult.success({
                "type": "text",
                "content": content,
                "offset": offset,
                "limit": limit,
                "path": cur_path,
            })
    elif os.path.isdir(cur_path):
        dir_list = []
        for target in os.listdir(cur_path):
            target_path = os.path.join(cur_path, target)
            dir_list.append({
                "type":"dir" if os.path.isdir(target_path) else "file",
                "name":target,
                "path":target_path
            })
        return ToolResult.success({
            "type": "directory",
            "path": cur_path,
            "listdir": dir_list,
        })
    return ToolResult.failure(
        "PATH_NOT_FOUND",
        "目标路径不存在",
        details={"path": cur_path},
    )


REGISTER = Tool({
        "type":"function",
        "name":"read",
        "description":"读取图片，文本文件或者目录",
        "parameters":{
            "type":"object",
            "properties":{
                "target_path":{
                    "type":"string",
                    "description":"传相对路径或者绝对路径，推荐使用相对路径，相对路径相对于当前工作目录的路径"
                },
                "offset":{
                    "type":"number",
                    "description":"读取文档的偏移量"
                },
                "limit":{
                    "type":"number",
                    "description":"读取的字符数量, 默认值为5000"
                }
            },
            "required":["target_path"],
            "additionalProperties": False
        }
    },read)
