"""Read Tool 的文本分页、硬限制与 cursor 契约测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from session.ExecutionContext import ExecutionContext  # noqa: E402
from tools.read import REGISTER as READ_TOOL  # noqa: E402
from tools.tools import Tools  # noqa: E402
from tools.types import ToolCallPreparationError  # noqa: E402


class ReadToolTests(unittest.TestCase):
    """验证文本读取不能突破本地限制，并可稳定续读。"""

    def setUp(self) -> None:
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root = Path(self.workspace.name)
        self.tools = Tools(
            ExecutionContext(
                self.workspace.name,
                "agent_1",
                "session_1",
                max_tool_call_length=8,
            )
        )
        self.tools.register(READ_TOOL)
        self._call_no = 0

    def call_read(self, arguments: dict):
        self._call_no += 1
        call = self.tools.prepare_call("read", arguments, f"call_{self._call_no}")
        return self.tools.execute(call)

    def test_reads_regular_text_by_line_and_resumes_from_cursor(self) -> None:
        """普通源码应按行返回，cursor 应从下一行继续而不是重读。"""
        (self.root / "source.py").write_text("a\nb\nc\n", encoding="utf-8")

        first = self.call_read({"target_path": "source.py", "limit": 2})

        self.assertEqual(first.status, "ok")
        self.assertEqual(first.data["content"], "a\nb\n")
        self.assertEqual(first.data["start_line"], 1)
        self.assertEqual(first.data["end_line"], 2)
        self.assertTrue(first.data["truncated"])
        self.assertEqual(first.data["truncation_reason"], "max_lines")
        self.assertFalse(first.data["continues_line"])
        self.assertIsInstance(first.data["next_cursor"], str)

        second = self.call_read(
            {"target_path": "source.py", "cursor": first.data["next_cursor"], "limit": 2}
        )

        self.assertEqual(second.status, "ok")
        self.assertEqual(second.data["content"], "c\n")
        self.assertEqual(second.data["start_line"], 3)
        self.assertFalse(second.data["truncated"])
        self.assertIsNone(second.data["next_cursor"])

    def test_caps_a_single_long_line_and_resumes_without_losing_characters(self) -> None:
        """min.js 这类单行文件必须受字符上限约束且可以无损续读。"""
        (self.root / "bundle.min.js").write_text("abcdefghijkl", encoding="utf-8")

        first = self.call_read({"target_path": "bundle.min.js", "limit": 10})

        self.assertEqual(first.status, "ok")
        self.assertEqual(first.data["content"], "abcdefgh")
        self.assertTrue(first.data["truncated"])
        self.assertEqual(first.data["truncation_reason"], "max_chars")
        self.assertTrue(first.data["continues_line"])

        second = self.call_read(
            {
                "target_path": "bundle.min.js",
                "cursor": first.data["next_cursor"],
                "limit": 10,
            }
        )

        self.assertEqual(second.status, "ok")
        self.assertEqual(second.data["content"], "ijkl")
        self.assertFalse(second.data["truncated"])
        self.assertEqual(first.data["content"] + second.data["content"], "abcdefghijkl")

    def test_rejects_invalid_or_ambiguous_text_pagination_arguments(self) -> None:
        """模型不能用负数、布尔值或 cursor/start_line 组合绕过读取契约。"""
        (self.root / "source.py").write_text("a\n", encoding="utf-8")

        for arguments in (
            {"target_path": "source.py", "limit": -1},
            {"target_path": "source.py", "limit": True},
            {"target_path": "source.py", "start_line": 0},
            {"target_path": "source.py", "cursor": "cursor", "start_line": 1},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ToolCallPreparationError) as raised:
                    self.tools.prepare_call("read", arguments, "invalid")
                self.assertEqual(raised.exception.error.code, "INVALID_ARGUMENTS")

    def test_rejects_a_cursor_after_the_file_changes(self) -> None:
        """不能把旧版本和新版本文件内容拼接成一份模型输入。"""
        path = self.root / "source.py"
        path.write_text("a\nb\nc\n", encoding="utf-8")
        first = self.call_read({"target_path": "source.py", "limit": 1})
        path.write_text("changed\n", encoding="utf-8")

        result = self.call_read(
            {"target_path": "source.py", "cursor": first.data["next_cursor"], "limit": 1}
        )

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_CHANGED")

    def test_paginates_directories_in_a_stable_order(self) -> None:
        """目录必须受本地条目上限约束，并能按 cursor 稳定续读。"""
        (self.root / "charlie.txt").write_text("", encoding="utf-8")
        (self.root / "alpha.txt").write_text("", encoding="utf-8")
        (self.root / "bravo.txt").write_text("", encoding="utf-8")
        self.tools = Tools(
            ExecutionContext(
                self.workspace.name,
                "agent_1",
                "session_1",
                max_tool_call_length=1_000,
                max_directory_entries=2,
            )
        )
        self.tools.register(READ_TOOL)

        first = self.call_read({"target_path": ".", "limit": 10})

        self.assertEqual(first.status, "ok")
        self.assertEqual(
            [entry["name"] for entry in first.data["entries"]],
            ["alpha.txt", "bravo.txt"],
        )
        self.assertEqual(first.data["effective_limit"], 2)
        self.assertTrue(first.data["truncated"])
        self.assertEqual(first.data["truncation_reason"], "max_entries")

        second = self.call_read(
            {"target_path": ".", "cursor": first.data["next_cursor"], "limit": 10}
        )

        self.assertEqual([entry["name"] for entry in second.data["entries"]], ["charlie.txt"])
        self.assertFalse(second.data["truncated"])

    def test_rejects_a_directory_cursor_after_the_directory_changes(self) -> None:
        """目录分页不能把变化前后的不同排序结果拼接在一起。"""
        (self.root / "alpha.txt").write_text("", encoding="utf-8")
        (self.root / "bravo.txt").write_text("", encoding="utf-8")
        self.tools = Tools(
            ExecutionContext(
                self.workspace.name,
                "agent_1",
                "session_1",
                max_tool_call_length=1_000,
            )
        )
        self.tools.register(READ_TOOL)

        first = self.call_read({"target_path": ".", "limit": 1})
        (self.root / "charlie.txt").write_text("", encoding="utf-8")
        second = self.call_read(
            {"target_path": ".", "cursor": first.data["next_cursor"]}
        )

        self.assertEqual(first.status, "ok")
        self.assertEqual(second.status, "error")
        self.assertEqual(second.error.code, "FILE_CHANGED")

    def test_rejects_oversized_or_disguised_images_before_loading_them(self) -> None:
        """图片必须先受本地字节上限和文件签名校验保护。"""
        (self.root / "large.png").write_bytes(b"\x89PNG\r\n\x1a\nmore")
        (self.root / "fake.png").write_bytes(b"not png")
        self.tools = Tools(
            ExecutionContext(
                self.workspace.name,
                "agent_1",
                "session_1",
                max_image_bytes=8,
            )
        )
        self.tools.register(READ_TOOL)

        oversized = self.call_read({"target_path": "large.png"})
        disguised = self.call_read({"target_path": "fake.png"})

        self.assertEqual(oversized.status, "error")
        self.assertEqual(oversized.error.code, "FILE_TOO_LARGE")
        self.assertEqual(disguised.status, "error")
        self.assertEqual(disguised.error.code, "UNSUPPORTED_IMAGE_FORMAT")

    def test_accepts_each_declared_image_signature(self) -> None:
        """所有在 Schema 中声明支持的图片扩展名都必须匹配对应签名。"""
        images = {
            "image.png": (b"\x89PNG\r\n\x1a\n", "image/png"),
            "image.jpg": (b"\xff\xd8\xff", "image/jpeg"),
            "image.gif": (b"GIF89a", "image/gif"),
            "image.webp": (b"RIFF\x00\x00\x00\x00WEBP", "image/webp"),
            "image.bmp": (b"BM", "image/bmp"),
        }
        for name, (content, mime_type) in images.items():
            (self.root / name).write_bytes(content)

        for name, (_, mime_type) in images.items():
            with self.subTest(name=name):
                result = self.call_read({"target_path": name})
                self.assertEqual(result.status, "ok")
                self.assertEqual(result.attachments[0].media_type, mime_type)

    def test_rejects_a_directory_entry_that_cannot_fit_the_local_output_limit(self) -> None:
        """不能返回的单个目录条目不得产生永远无法推进的 cursor。"""
        (self.root / "very-long-file-name.txt").write_text("", encoding="utf-8")
        self.tools = Tools(
            ExecutionContext(
                self.workspace.name,
                "agent_1",
                "session_1",
                max_tool_call_length=10,
            )
        )
        self.tools.register(READ_TOOL)

        result = self.call_read({"target_path": "."})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "FILE_TOO_LARGE")

    def test_rejects_binary_files_instead_of_returning_corrupted_text(self) -> None:
        """含 NUL 的普通二进制文件不能被当作文本交给模型。"""
        (self.root / "data.bin").write_bytes(b"header\x00payload")

        result = self.call_read({"target_path": "data.bin"})

        self.assertEqual(result.status, "error")
        self.assertEqual(result.error.code, "UNSUPPORTED_FILE_TYPE")


if __name__ == "__main__":
    unittest.main()
