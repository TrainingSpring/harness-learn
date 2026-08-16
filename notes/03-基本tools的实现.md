# 基础Tool的实现

从这里开始，我们参考一些[pi-agent](https://github.com/earendil-works/pi)的实现方式

## 什么是PI-Agent
PI是*Mario Zechner*开源的一个极简的Agent框架 ， 用Typescript编写， 也是小龙虾（OpenClaw）的核心框架。 


# 核心tool

> 在Pi中， 仅仅只内置了4个工具： read , write , edit , bash。 
>
> 这几项基本能涵盖日常的任务需求了。有其他tool的时候，再新增即可。 
>
> read 读取能力
>
> write 写入能力
>
> edit  编辑能力
>
> bash  终端命令能力


我曾想过一个问题， 其实bash已经可以做到读，写和编辑了， 为啥还要自定义这些能力呢？ 

我查阅了一些资料，给的答案大概就是： 

bash很强大，若有条件，甚至可以做任何事， 读写改只是基本操作，完全可以胜任 ， 但就是因为它的强大， 所以导致很多安全边界性的问题。
比如可能执行危险指令，读取内容会撑爆上下文窗口，复杂命令LLM可能会写错，命令的选择也会增加推理成本等。 

而日常使用的agent中，使用频率高的无非读，写，编辑 ， 直接告诉LLM有这些工具， 大模型只需要去选工具，和填参数， 而不用再去推理用什么命令好，怎么组合命令， 怎么过滤等等。 

简单说就是让大模型从写作文，变成了做选择和填空题。


# Read 读文件工具

> 对于大模型而言，最主要的就是文本数据， 当然目前的多模态大模型也能理解图片和音频。
> 
> 读取内容以文本文档为主， 同时兼容图片，其他类型的文件也类似。 
> 
> 目录范围，一般以工作目录为根目录


## 思路

要支持读文件也要支持读文件目录。 
如果传递的路径是目录路径，就返回目录列表， 
如果大模型传递的路径是文件路径，根据文件类型传递不同的内容。
由于大模型上下文窗口的限制， 许多大文件一次性返回所有内容，容易撑爆上下文窗口，所以要着重处理。 


### 参数
1. 路径， 一般使用相对路径，当然也可以支持绝对路径（这里取决于对agent的定义）。
2. 偏移，因为上下文窗口大小的限制， 不可能一次性将一个超大文件的内容一次性返回， 这里可能就要用到分批次读取，这个偏移就是起始位置
3. 长度， 当前批次要读取到的文本内容的长度。 

### 实现

1. 判定是否是相对路径（取决于是否支持绝对路径，最好还是支持的，LLM如果返回绝对路径会很麻烦）
2. 判断是否是目录，如果是目录就返回目录列表，
3. 如果不是目录，则判定文件类型
    - 是否是图片，如果是图片则将图片转换为base64，以input_image类型发给大模型。
    - 是否是音频，将音频也转换为base64，以input_audio类型发给大模型。
    - 否则判定就是文本类型，并将读取到的内容发送给大模型。

## 代码实现

我想了一下， 对于工作目录，应该是基于Agent的，而不是基于read工具的， 所以我将工作目录放到了Agent Loop中， 在tool注册时注入示例信息，这样tool就能访问Agent的基本信息了
 
`read.py`
```python
import os.path
import base64
import mimetypes
from tools.types import Tool
from loop.loop import AgentLoop
IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif",
    ".webp", ".bmp"
}
# 根据文件扩展名判定是否是图片
def is_img(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def read(self:AgentLoop,target_path:str,offset=None,limit=None):
    cur_path = target_path
    # 判定是否是相对路径
    if not os.path.isabs(target_path):
        cur_path = os.path.join(self.workspace,target_path)
    # 判定路径是文件路径还是目录路径
    if os.path.isfile(cur_path):
        if not os.path.exists(cur_path):
            return "File not found"

        if is_img(cur_path):
            mime_type, _ = mimetypes.guess_type(cur_path)
            if mime_type is not None:
                image_types = None;
                with open(cur_path, 'rb') as file:
                    image_types = file.read()
                image_base64 = base64.b64encode(image_types).decode("ascii")
                return [
                    {
                        "type":"text",
                        "text":f"读取到图片{mime_type or ""}",
                    },
                    {
                        "type":"input_image",
                        "image_url":f"data:{mime_type};base64,{image_base64}"
                    }
                ]
            return [
                {
                    "type":"input_text",
                    "text":"图片格式未知!",
                    "error":True
                }
            ]
        with open(cur_path, 'r', encoding='utf-8') as f:
            f.seek(offset or 0)
            content = f.read(limit)
            return [
                {
                    "type":"input_text",
                    "text":content,
                    "offset":offset,
                    "limit":limit,
                    "path":cur_path
                }
            ]
    elif os.path.isdir(cur_path):
        return [
            {
                "type":"text",
                "text":f"读取到目录{cur_path}",
            },
            {
                "type":"input_text",
                "path":cur_path,
                "text":os.listdir(cur_path)
            }
        ]
```