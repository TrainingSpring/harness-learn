"""Edit Tool 的参数、文本变换与版本前置条件测试。"""

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.edit import REGISTER as EDIT_TOOL  # noqa: E402
from tools.edit import edit  # noqa: E402
from tools.files.version import file_version  # noqa: E402
from tools.files.mutation import acquire_file_mutation_lock  # noqa: E402
from tools.read import read  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import ToolCallPreparationError  # noqa: E402
from tools.write import write  # noqa: E402


class EditToolTests(unittest.TestCase):
    """验证 edit 只能基于已读取版本执行可验证的文本替换。"""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.ctx = ExecutionContext(self.workspace.name, "agent_1", "session_1")
        self.tools = Tools(self.ctx)
        self.tools.register(EDIT_TOOL)
        self._call_number = 0

    def call_edit(self, arguments: dict):
        self._call_number += 1
        call = self.tools.prepare_call("edit", arguments, f"edit-{self._call_number}")
        return self.tools.execute(call)

    def test_rejects_invalid_arguments_before_permission_check(self) -> None:
        """缺失、宽松类型和未知字段必须在工具执行前被拒绝。"""
        invalid_arguments = (
            {"target_path": "source.txt", "edits": []},
            {
                "target_path": "source.txt",
                "expected_version": "v1",
                "edits": [],
            },
            {
                "target_path": "source.txt",
                "expected_version": "v1",
                "edits": [{"old_text": "before"}],
            },
            {
                "target_path": "source.txt",
                "expected_version": "v1",
                "edits": [{"old_text": "", "new_text": "after"}],
            },
            {
                "target_path": "source.txt",
                "expected_version": "v1",
                "edits": [
                    {"old_text": "before", "new_text": "after", "replace_all": "false"}
                ],
            },
            {
                "target_path": "source.txt",
                "expected_version": "v1",
                "edits": [{"old_text": "before", "new_text": "after", "extra": True}],
            },
            {
                "target_path": "source.txt",
                "expected_version": "v1",
                "edits": [{"old_text": "before", "new_text": "after"}],
                "extra": True,
            },
        )

        for arguments in invalid_arguments:
            with self.subTest(arguments=arguments):
                with self.assertRaises(ToolCallPreparationError) as raised:
                    self.tools.prepare_call("edit", arguments, "invalid-edit")
                self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_applies_a_unique_replacement_with_a_required_file_version(self) -> None:
        """成功编辑必须回报新版本，并保留删除用的空 new_text 语义。"""
        target = self.root / "source.txt"
        target.write_text("before remove", encoding="utf-8")
        version = read(self.ctx, "source.txt").data["version"]

        result = self.call_edit(
            {
                "target_path": "source.txt",
                "expected_version": version,
                "edits": [
                    {"old_text": "before", "new_text": "after"},
                    {"old_text": " remove", "new_text": ""},
                ],
            }
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(target.read_text(encoding="utf-8"), "after")
        self.assertEqual(result.data["operation"], "edited")
        self.assertEqual(result.data["edit_count"], 2)
        self.assertEqual(result.data["replacement_count"], 2)
        self.assertTrue(result.data["precondition_checked"])
        self.assertIsInstance(result.data["version"], str)

    def test_rejects_stale_versions_without_modifying_the_file(self) -> None:
        """编辑不能覆盖 read 之后发生的外部修改。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")
        stale_version = file_version(target)
        target.write_text("external", encoding="utf-8")

        result = edit(
            self.ctx,
            "source.txt",
            stale_version,
            [{"old_text": "external", "new_text": "agent"}],
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_CHANGED")
        self.assertEqual(target.read_text(encoding="utf-8"), "external")

    def test_rejects_missing_and_ambiguous_text_without_leaking_source_text(self) -> None:
        """定位失败应给稳定错误码，且消息不回显模型传入的完整文本。"""
        target = self.root / "source.txt"
        target.write_text("duplicate duplicate", encoding="utf-8")
        version = file_version(target)

        missing = edit(
            self.ctx,
            "source.txt",
            version,
            [{"old_text": "secret-not-present", "new_text": "next"}],
        )
        ambiguous = edit(
            self.ctx,
            "source.txt",
            version,
            [{"old_text": "duplicate", "new_text": "next"}],
        )

        self.assertEqual(missing.error.code, "EDIT_TEXT_NOT_FOUND")
        self.assertEqual(ambiguous.error.code, "EDIT_TEXT_AMBIGUOUS")
        self.assertNotIn("secret-not-present", missing.error.message)
        self.assertEqual(target.read_text(encoding="utf-8"), "duplicate duplicate")

    def test_replaces_all_matches_and_allows_later_edits_to_use_prior_results(self) -> None:
        """replace_all 应替换所有文本，后续编辑应读取前一条编辑后的内存内容。"""
        target = self.root / "source.txt"
        target.write_text("old old", encoding="utf-8")

        result = edit(
            self.ctx,
            "source.txt",
            file_version(target),
            [
                {"old_text": "old", "new_text": "new", "replace_all": True},
                {"old_text": "new new", "new_text": "final"},
            ],
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.data["replacement_count"], 3)
        self.assertEqual(target.read_text(encoding="utf-8"), "final")

    def test_rejects_directories_as_edit_targets(self) -> None:
        """目录不能被当作文本文件编辑。"""
        target = self.root / "directory"
        target.mkdir()

        result = edit(
            self.ctx,
            "directory",
            "version",
            [{"old_text": "before", "new_text": "after"}],
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "TARGET_IS_DIRECTORY")

    def test_applies_all_edits_in_memory_before_changing_the_file(self) -> None:
        """后续编辑失败时，先前在内存中的成功替换不能部分落盘。"""
        target = self.root / "source.txt"
        target.write_text("first", encoding="utf-8")
        version = file_version(target)

        result = edit(
            self.ctx,
            "source.txt",
            version,
            [
                {"old_text": "first", "new_text": "second"},
                {"old_text": "missing", "new_text": "third"},
            ],
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "EDIT_TEXT_NOT_FOUND")
        self.assertEqual(target.read_text(encoding="utf-8"), "first")

    def test_rejects_unsupported_or_oversized_source_without_modifying_it(self) -> None:
        """Edit 只能完整读取受本地上限保护的 UTF-8 非 NUL 文本。"""
        cases = {
            "nul.txt": b"before\x00",
            "binary.txt": b"\xff\xfe",
            "large.txt": b"before!",
        }
        for name, content in cases.items():
            (self.root / name).write_bytes(content)
        limited_ctx = ExecutionContext(
            self.workspace.name,
            "agent_1",
            "session_1",
            max_edit_source_bytes=6,
        )

        nul = edit(
            self.ctx,
            "nul.txt",
            file_version(self.root / "nul.txt"),
            [{"old_text": "before", "new_text": "after"}],
        )
        binary = edit(
            self.ctx,
            "binary.txt",
            file_version(self.root / "binary.txt"),
            [{"old_text": "before", "new_text": "after"}],
        )
        large = edit(
            limited_ctx,
            "large.txt",
            file_version(self.root / "large.txt"),
            [{"old_text": "before", "new_text": "after"}],
        )

        self.assertEqual(nul.error.code, "UNSUPPORTED_FILE_TYPE")
        self.assertEqual(binary.error.code, "UNSUPPORTED_TEXT_ENCODING")
        self.assertEqual(large.error.code, "FILE_TOO_LARGE")
        self.assertEqual((self.root / "nul.txt").read_bytes(), cases["nul.txt"])
        self.assertEqual((self.root / "binary.txt").read_bytes(), cases["binary.txt"])
        self.assertEqual((self.root / "large.txt").read_bytes(), cases["large.txt"])

    def test_preserves_bom_and_newline_bytes_outside_the_replacement(self) -> None:
        """局部替换不能把 UTF-8 BOM 或 CRLF 格式意外规范化。"""
        target = self.root / "source.txt"
        target.write_bytes(b"\xef\xbb\xbfbefore\r\n")

        result = edit(
            self.ctx,
            "source.txt",
            file_version(target),
            [{"old_text": "before", "new_text": "after"}],
        )

        self.assertEqual(result.status, "ok")
        self.assertEqual(target.read_bytes(), b"\xef\xbb\xbfafter\r\n")

    def test_keeps_original_file_and_cleans_temporary_file_when_replace_fails(self) -> None:
        """原子替换失败不得截断原文件，也不能遗留提交临时文件。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")

        with patch("tools.files.mutation.os.replace", side_effect=OSError("failed")):
            result = edit(
                self.ctx,
                "source.txt",
                file_version(target),
                [{"old_text": "before", "new_text": "after"}],
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "EDIT_FILE_FAILED")
        self.assertEqual(target.read_text(encoding="utf-8"), "before")
        self.assertEqual(list(self.root.glob(".source.txt.*.tmp")), [])

    def test_returns_file_busy_when_the_same_path_commit_lock_times_out(self) -> None:
        """当前进程内另一项提交持锁时，Edit 必须快速返回可重试错误。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")
        limited_ctx = ExecutionContext(
            self.workspace.name,
            "agent_1",
            "session_1",
            file_mutation_lock_timeout_seconds=0.001,
        )

        with acquire_file_mutation_lock(str(target), timeout_seconds=1):
            result = edit(
                limited_ctx,
                "source.txt",
                file_version(target),
                [{"old_text": "before", "new_text": "after"}],
            )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_BUSY")
        self.assertTrue(result.error.retryable)
        self.assertEqual(target.read_text(encoding="utf-8"), "before")

    def test_a_lock_on_another_path_does_not_block_edit(self) -> None:
        """提交协调按真实路径隔离，不应把不同文件串行化。"""
        locked = self.root / "locked.txt"
        target = self.root / "source.txt"
        locked.write_text("locked", encoding="utf-8")
        target.write_text("before", encoding="utf-8")
        limited_ctx = ExecutionContext(
            self.workspace.name,
            "agent_1",
            "session_1",
            file_mutation_lock_timeout_seconds=0.001,
        )

        with acquire_file_mutation_lock(str(locked), timeout_seconds=1):
            result = edit(
                limited_ctx,
                "source.txt",
                file_version(target),
                [{"old_text": "before", "new_text": "after"}],
            )

        self.assertEqual(result.status, "ok")
        self.assertEqual(target.read_text(encoding="utf-8"), "after")

    def test_two_same_version_edits_cannot_both_commit(self) -> None:
        """同进程同版本竞争时，后提交者必须重新读取而不能静默覆盖。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")
        version = file_version(target)
        barrier = threading.Barrier(2)

        def perform(new_text: str):
            barrier.wait()
            return edit(
                self.ctx,
                "source.txt",
                version,
                [{"old_text": "before", "new_text": new_text}],
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(perform, ("first", "second")))

        self.assertEqual([result.status for result in results].count("ok"), 1)
        self.assertEqual(
            [result.error.code for result in results if result.status == "error"],
            ["FILE_CHANGED"],
        )
        self.assertIn(target.read_text(encoding="utf-8"), {"first", "second"})

    def test_write_and_edit_with_the_same_version_cannot_both_commit(self) -> None:
        """共享提交锁必须同时覆盖完整覆盖和局部编辑两种工具。"""
        target = self.root / "source.txt"
        target.write_text("before", encoding="utf-8")
        version = read(self.ctx, "source.txt").data["version"]
        barrier = threading.Barrier(2)

        def perform_edit():
            barrier.wait()
            return edit(
                self.ctx,
                "source.txt",
                version,
                [{"old_text": "before", "new_text": "edited"}],
            )

        def perform_write():
            barrier.wait()
            return write(self.ctx, "source.txt", "written", expected_version=version)

        with ThreadPoolExecutor(max_workers=2) as executor:
            edit_future = executor.submit(perform_edit)
            write_future = executor.submit(perform_write)
            results = [edit_future.result(), write_future.result()]

        self.assertEqual([result.status for result in results].count("ok"), 1)
        self.assertEqual(
            [result.error.code for result in results if result.status == "error"],
            ["FILE_CHANGED"],
        )
        self.assertIn(target.read_text(encoding="utf-8"), {"edited", "written"})

    def test_rejects_too_many_edits_and_oversized_edit_output(self) -> None:
        """条数和最终 UTF-8 字节数均须服从本地硬上限。"""
        target = self.root / "source.txt"
        target.write_text("a", encoding="utf-8")
        constrained_ctx = ExecutionContext(
            self.workspace.name,
            "agent_1",
            "session_1",
            max_edit_operations=1,
            max_write_bytes=2,
        )
        version = file_version(target)

        too_many = edit(
            constrained_ctx,
            "source.txt",
            version,
            [
                {"old_text": "a", "new_text": "b"},
                {"old_text": "b", "new_text": "c"},
            ],
        )
        too_large = edit(
            constrained_ctx,
            "source.txt",
            version,
            [{"old_text": "a", "new_text": "中文"}],
        )

        self.assertEqual(too_many.error.code, "INVALID_ARGUMENTS")
        self.assertEqual(too_large.error.code, "FILE_TOO_LARGE")
        self.assertEqual(target.read_text(encoding="utf-8"), "a")


if __name__ == "__main__":
    unittest.main()
