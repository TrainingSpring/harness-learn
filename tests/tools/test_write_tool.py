"""Write Tool 的输入、原子替换与版本前置条件测试。"""

import sys
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.read import read  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import ToolCallPreparationError  # noqa: E402
from tools.write import REGISTER as WRITE_TOOL  # noqa: E402
from tools.write import write  # noqa: E402


class WriteToolTests(unittest.TestCase):
    """验证 write 只能原子地创建或完整替换受限文本文件。"""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.ctx = ExecutionContext(self.workspace.name, "agent_1", "session_1")
        self.tools = Tools(self.ctx)
        self.tools.register(WRITE_TOOL)

    def test_rejects_missing_or_invalid_write_arguments_before_permission_check(self) -> None:
        """content 是必填文本，模型不能靠空值或未知字段进入执行层。"""
        for arguments in (
            {"target_path": "file.txt"},
            {"target_path": "", "content": "text"},
            {"target_path": "file.txt", "content": 1},
            {"target_path": "file.txt", "content": "text", "expected_version": ""},
            {"target_path": "file.txt", "content": "text", "unknown": True},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ToolCallPreparationError) as raised:
                    self.tools.prepare_call("write", arguments, "write-invalid")
                self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_creates_parent_directories_and_reports_utf8_byte_count(self) -> None:
        """write 创建文件时返回真实字节数和新版本，而非 Python 字符数。"""
        result = write(self.ctx, "nested/new.txt", "中文")

        target = self.root / "nested" / "new.txt"
        self.assertEqual(result.status, "ok")
        self.assertEqual(target.read_text(encoding="utf-8"), "中文")
        self.assertEqual(result.data["operation"], "created")
        self.assertEqual(result.data["bytes_written"], len("中文".encode("utf-8")))
        self.assertIsInstance(result.data["version"], str)
        self.assertFalse(result.data["precondition_checked"])

    def test_rejects_content_larger_than_the_local_byte_limit(self) -> None:
        """本地 UTF-8 字节上限不能被多字节字符绕过。"""
        limited_ctx = ExecutionContext(
            self.workspace.name,
            "agent_1",
            "session_1",
            max_write_bytes=5,
        )

        result = write(limited_ctx, "large.txt", "中文")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_TOO_LARGE")
        self.assertFalse((self.root / "large.txt").exists())

    def test_replaces_only_when_the_expected_version_is_current(self) -> None:
        """有版本前置条件时，外部修改后不得静默覆盖新内容。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")
        version = read(self.ctx, "source.txt").data["version"]

        replaced = write(self.ctx, "source.txt", "after", expected_version=version)
        target.write_text("external", encoding="utf-8")
        stale = write(self.ctx, "source.txt", "should-not-write", expected_version=version)

        self.assertEqual(replaced.status, "ok")
        self.assertEqual(replaced.data["operation"], "replaced")
        self.assertTrue(replaced.data["precondition_checked"])
        self.assertEqual(stale.status, "error")
        self.assertEqual(stale.error.code, "FILE_CHANGED")
        self.assertEqual(target.read_text(encoding="utf-8"), "external")

    def test_refuses_to_replace_when_target_appears_during_new_file_write(self) -> None:
        """临时文件写入期间出现的目标不能被不带前置条件的调用覆盖。"""
        target = self.root / "appeared.txt"

        def create_external_file(_descriptor: int) -> None:
            target.write_text("external", encoding="utf-8")

        with patch("tools.write.os.fsync", side_effect=create_external_file):
            result = write(self.ctx, "appeared.txt", "agent")

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_CHANGED")
        self.assertEqual(target.read_text(encoding="utf-8"), "external")

    def test_refuses_to_replace_when_target_disappears_during_versioned_write(self) -> None:
        """带版本写入的目标在临时文件写入后消失时也必须拒绝。"""
        target = self.root / "deleted.txt"
        target.write_text("before", encoding="utf-8")
        version = read(self.ctx, "deleted.txt").data["version"]

        def delete_target(_descriptor: int) -> None:
            target.unlink()

        with patch("tools.write.os.fsync", side_effect=delete_target):
            result = write(self.ctx, "deleted.txt", "agent", expected_version=version)

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_CHANGED")
        self.assertFalse(target.exists())

    @unittest.skipIf(os.name == "nt", "Windows 不提供与 POSIX 相同的权限位语义")
    def test_replacement_preserves_existing_file_permission_bits(self) -> None:
        """原子替换不应把既有文件权限意外收缩为临时文件默认值。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")
        target.chmod(0o640)

        result = write(self.ctx, "source.txt", "after")

        self.assertEqual(result.status, "ok")
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)

    def test_rejects_directories_and_preserves_original_file_when_replace_fails(self) -> None:
        """目录不是 write 目标，替换失败也不能截断原文件。"""
        (self.root / "directory").mkdir()
        directory_result = write(self.ctx, "directory", "content")
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")

        with patch("tools.write.os.replace", side_effect=OSError("replace failed")):
            failed_replace = write(self.ctx, "source.txt", "after")

        self.assertEqual(directory_result.status, "error")
        self.assertEqual(directory_result.error.code, "TARGET_IS_DIRECTORY")
        self.assertEqual(failed_replace.status, "error")
        self.assertEqual(failed_replace.error.code, "WRITE_FILE_FAILED")
        self.assertEqual(target.read_text(encoding="utf-8"), "before")
        self.assertEqual(list(self.root.glob(".source.txt.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
