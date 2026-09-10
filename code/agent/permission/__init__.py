"""权限模块的稳定公共导出。

外部调用方应从此处导入公共类型，而不是依赖权限模块内部的文件布局。
"""

from .PermissionManager import PermissionManager
from .types import (
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    PermissionRequirement,
    PermissionRequest,
    PermissionResponse,
    PermissionRule,
    PermissionScope,
)

__all__ = [
    "PermissionAction",
    "PermissionDecision",
    "PermissionManager",
    "PermissionMode",
    "PermissionRequirement",
    "PermissionRequest",
    "PermissionResponse",
    "PermissionRule",
    "PermissionScope",
]
