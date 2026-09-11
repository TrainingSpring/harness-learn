"""持久化层使用的稳定异常类型。"""


class StorageError(Exception):
    """所有持久化错误的基类，供上层统一捕获。"""


class StorageSchemaError(StorageError):
    """数据库 schema 版本不兼容或迁移失败。"""


class StorageFormatError(StorageError):
    """数据库字段或 JSON 数据格式非法。"""


class StorageConflictError(StorageError):
    """数据违反唯一约束或发生状态冲突。"""


class CredentialResolutionError(StorageError):
    """凭据引用无法解析为实际凭据。"""
