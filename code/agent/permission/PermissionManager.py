import json

from permission.types import PermissionRequirement
from runtime.ExecutionContext import ExecutionContext


class PermissionManager:
    """权限规则管理器的临时入口。

    当前阶段仅完成类型迁移，具体的规则匹配、模式策略和用户确认会在
    下一增量中实现。保留此类的构造方式，使 Agent 组装路径在迁移期间
    仍然完整。
    """

    def __init__(self, ctx: ExecutionContext):
        """保存执行上下文，供下一阶段创建规则管理器时迁移使用。

        Args:
            ctx: 当前 Agent 的执行环境。后续 Manager 会改为直接接收
                模式和策略，而每次 check 从 PermissionRequest 获取身份。
        """
        self.ctx = ctx
        self.allow_list = []

    @staticmethod
    def _args_str_to_dict(arguments: str | dict) -> dict:
        """将旧调用链传入的 JSON 字符串转换为字典。

        此方法会在下一阶段删除；那时 JSON 解析将由 Tools.prepare_call
        统一负责，PermissionManager 只接收 PermissionRequest。

        Args:
            arguments: 旧 Runtime 传入的原始工具参数。

        Returns:
            解析后的参数字典。
        """
        if isinstance(arguments, str):
            return json.loads(arguments)
        if not isinstance(arguments, dict):
            raise ValueError("[PermissionManager Error] arguments must be str or dict")
        return arguments

    def check(self, permission: PermissionRequirement, arguments: str | dict) -> None:
        """保留旧检查入口，等待下一阶段替换为 PermissionRequest 决策。

        Args:
            permission: 工具的静态权限需求。
            arguments: 原始工具参数。
        """
        args = self._args_str_to_dict(arguments)
        if permission.resource_from is not None:
            args[permission.resource_from]





