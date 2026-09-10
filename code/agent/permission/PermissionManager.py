import json
from dataclasses import dataclass
from enum import Enum

from runtime.ExecutionContext import ExecutionContext


class PermissionAction(Enum):
    """
    权限动作
    """
    file_read="filesystem.read"
    file_write="filesystem.write"
    bash_execute="bash.execute"

@dataclass
class Permission:
    """
    tool中使用的权限类,为了统一数据格式
    """
    action:PermissionAction
    resource_from:str


class PermissionType(Enum):
    """
    权限类型
    allow:允许
    deny:拒绝
    ask:询问
    """
    allow="allow"
    deny="deny"
    ask="ask"


class PermissionManager:
    """
    权限管理器,主要做权限的写入,检查
    """
    def __init__(self,ctx:ExecutionContext):
        self.ctx = ctx
        self.allow_list = []
    @staticmethod
    def _args_str_to_dict(arguments:str|dict):
        """
        将参数统一处理成字典
        :param arguments: str|dict
        :return: dict
        """
        if isinstance(arguments,str):
            return json.loads(arguments)
        elif not isinstance(arguments,dict):
            raise ValueError("[PermissionManager Error] arguments must be str or dict")
        return arguments

    def check(self,permission:Permission,arguments:str|dict)->PermissionType:
        args = self._args_str_to_dict(arguments)
        data = args[permission.resource_from]
        pass






