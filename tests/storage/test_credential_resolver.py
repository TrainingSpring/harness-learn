"""CredentialResolver 的凭据引用解析测试。"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from head.credential_resolver import CredentialResolver  # noqa: E402
from storage.errors import CredentialResolutionError  # noqa: E402


class CredentialResolverTests(unittest.TestCase):
    """验证凭据只通过引用解析，不把密钥写入配置对象。"""

    def setUp(self):
        """创建解析器。"""
        self.resolver = CredentialResolver()

    def test_resolve_env_reference(self):
        """env 引用应读取对应环境变量。"""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-value"}):
            self.assertEqual(
                self.resolver.resolve("env:OPENAI_API_KEY"),
                "secret-value",
            )

    def test_missing_env_reference_raises(self):
        """缺少环境变量时必须明确失败。"""
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(CredentialResolutionError):
                self.resolver.resolve("env:OPENAI_API_KEY")

    def test_unsupported_reference_scheme_raises(self):
        """首期不支持的凭据来源不能静默处理。"""
        with self.assertRaises(CredentialResolutionError):
            self.resolver.resolve("file:/tmp/api-key")

    def test_invalid_environment_variable_name_raises(self):
        """环境变量名必须是合法标识符，防止引用语义不清。"""
        with self.assertRaises(CredentialResolutionError):
            self.resolver.resolve("env:OPENAI-API-KEY")


if __name__ == "__main__":
    unittest.main()
