"""LLM 凭据引用解析器。"""

import os
import re

from storage.errors import CredentialResolutionError


class CredentialResolver:
    """将安全的凭据引用解析为本次运行内存中的实际凭据。

    首期只支持 env:VARIABLE_NAME 格式。解析结果只返回给运行时调用方，
    不会回写 LLMProfile 或任何持久化数据。
    """

    _ENV_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

    def resolve(self, credential_ref: str) -> str:
        """解析环境变量引用。

        Args:
            credential_ref: 形如 env:OPENAI_API_KEY 的引用。

        Returns:
            环境变量中的实际凭据字符串。

        Raises:
            CredentialResolutionError: 引用格式不支持、变量名非法或变量缺失。
        """
        if not isinstance(credential_ref, str) or not credential_ref.startswith("env:"):
            raise CredentialResolutionError(
                "当前只支持 env:VARIABLE_NAME 格式的凭据引用"
            )

        variable_name = credential_ref[4:]
        if self._ENV_NAME_PATTERN.fullmatch(variable_name) is None:
            raise CredentialResolutionError(
                f"非法的环境变量凭据引用: {credential_ref}"
            )

        value = os.environ.get(variable_name)
        if not value:
            raise CredentialResolutionError(
                f"凭据环境变量不存在或为空: {variable_name}"
            )
        return value
