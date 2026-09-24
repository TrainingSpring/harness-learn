"""ToolCatalog 的工具发现和动态加载测试。"""

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from tools.registry.catalog import ToolCatalog  # noqa: E402
from tools.types import Tool  # noqa: E402


class ToolCatalogTests(unittest.TestCase):
    """验证工具只能从代码注册模块中加载。"""

    def setUp(self):
        """创建工具目录。"""
        self.catalog = ToolCatalog()

    def test_get_loads_registered_tool_by_name(self):
        """按名称加载工具应返回经过校验的 Tool 对象。"""
        tool = self.catalog.get("read")

        self.assertIsInstance(tool, Tool)
        self.assertEqual(tool.schema["name"], "read")

    def test_get_rejects_unknown_tool(self):
        """不存在的工具不能被配置加载。"""
        with self.assertRaises(ValueError):
            self.catalog.get("not_registered")

    def test_list_available_contains_code_registered_tools(self):
        """工具列表应发现当前代码中的有效 REGISTER。"""
        names = {metadata.name for metadata in self.catalog.list_available()}

        self.assertEqual(names, {"read", "write", "edit", "bash"})
        self.assertNotIn("types", names)
        for name in ("process_start", "process_status", "process_logs", "process_wait", "process_stop"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.catalog.get(name)

    def test_validate_names_rejects_unknown_name(self):
        """批量校验应一次性拒绝未知工具名称。"""
        with self.assertRaises(ValueError):
            self.catalog.validate_names(["read", "not_registered"])


if __name__ == "__main__":
    unittest.main()
