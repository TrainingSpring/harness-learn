"""生成和校验可跨数据库迁移的持久化实体 ID。"""

import re
import secrets
import string


_RANDOM_ALPHABET = string.ascii_uppercase + string.digits
_RANDOM_LENGTH = 10
_SUPPORTED_PREFIXES = frozenset(
    {
        "agent",
        "llm",
        "session",
        "item",
        "delegation",
        "permission_rule",
    }
)


def generate_id(prefix: str) -> str:
    """生成指定实体类型的前缀随机 ID。

    Args:
        prefix: 实体类型前缀，例如 ``agent`` 或 ``session``。

    Returns:
        形如 ``agent_1V3ASAXQ2A`` 的 ID。

    Raises:
        ValueError: prefix 不是受支持的实体类型时抛出。
    """
    if prefix not in _SUPPORTED_PREFIXES:
        raise ValueError(f"不支持的 ID 前缀: {prefix}")

    random_part = "".join(
        secrets.choice(_RANDOM_ALPHABET) for _ in range(_RANDOM_LENGTH)
    )
    return f"{prefix}_{random_part}"


def validate_id(entity_type: str, value: str) -> str:
    """校验 ID 是否匹配指定实体类型，并返回原值。

    Args:
        entity_type: 实体类型前缀，例如 ``agent``。
        value: 待校验的 ID。

    Returns:
        通过校验的原始 ID，便于在构造对象时直接使用。

    Raises:
        ValueError: ID 类型、格式或随机部分长度不正确时抛出。
    """
    if entity_type not in _SUPPORTED_PREFIXES:
        raise ValueError(f"不支持的 ID 前缀: {entity_type}")
    if not isinstance(value, str):
        raise ValueError(f"{entity_type} ID 必须是字符串")

    pattern = rf"^{re.escape(entity_type)}_[A-Z0-9]{{{_RANDOM_LENGTH}}}$"
    if re.fullmatch(pattern, value) is None:
        raise ValueError(f"非法的 {entity_type} ID: {value}")
    return value
