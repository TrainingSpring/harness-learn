"""生成用于文件读取续读与写入前置条件的不透明版本标识。"""

import base64
import json
import os


def file_version(path: str) -> str:
    """根据当前文件元数据生成稳定的单版本 token。"""
    stat = os.stat(path)
    payload = {
        "v": 1,
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")
