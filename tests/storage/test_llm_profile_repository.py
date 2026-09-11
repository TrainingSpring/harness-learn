"""LLMProfileRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.errors import StorageConflictError  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import LLMProfile  # noqa: E402


class LLMProfileRepositoryTests(unittest.TestCase):
    """验证 LLM 配置的持久化生命周期。"""

    def setUp(self):
        """为每个测试创建独立的临时数据库。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.repository = LLMProfileRepository(self.database)

    def tearDown(self):
        """关闭连接并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def make_profile(self, profile_id="llm_7KQ2M8P4XZ", name="代码模型"):
        """创建测试用 LLMProfile。"""
        return LLMProfile(
            id=profile_id,
            name=name,
            provider="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5",
            credential_ref="env:OPENAI_API_KEY",
            options={"temperature": 0.2},
        )

    def test_save_and_get_round_trip_preserves_configuration(self):
        """保存后读取应还原配置，且不需要保存 API Key。"""
        profile = self.repository.save(self.make_profile())

        loaded = self.repository.get(profile.id)

        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "代码模型")
        self.assertEqual(loaded.options, {"temperature": 0.2})
        self.assertEqual(loaded.credential_ref, "env:OPENAI_API_KEY")
        self.assertIsNotNone(loaded.created_at)
        self.assertIsNotNone(loaded.updated_at)
        self.assertFalse(hasattr(loaded, "api_key"))

    def test_save_updates_existing_profile_without_changing_identity(self):
        """相同 ID 保存时应更新记录，而不是创建重复配置。"""
        self.repository.save(self.make_profile())
        updated = self.repository.save(
            self.make_profile(name="更新后的模型")
        )

        loaded = self.repository.get(updated.id)
        self.assertEqual(loaded.name, "更新后的模型")
        self.assertEqual(
            self.repository.list_all(limit=10, offset=0),
            [loaded],
        )

    def test_duplicate_name_is_reported_as_storage_conflict(self):
        """不同 ID 不能使用同一个配置名称。"""
        self.repository.save(self.make_profile())

        with self.assertRaises(StorageConflictError):
            self.repository.save(
                self.make_profile(
                    profile_id="llm_8LRT3N5QYB",
                    name="代码模型",
                )
            )

    def test_list_all_supports_limit_and_offset(self):
        """列表读取必须支持分页。"""
        self.repository.save(self.make_profile())
        self.repository.save(
            self.make_profile(
                profile_id="llm_8LRT3N5QYB",
                name="摘要模型",
            )
        )

        page = self.repository.list_all(limit=1, offset=1)

        self.assertEqual(len(page), 1)
        self.assertEqual(page[0].name, "摘要模型")

    def test_delete_returns_whether_a_profile_existed(self):
        """删除已存在配置返回 True，重复删除返回 False。"""
        profile = self.repository.save(self.make_profile())

        self.assertTrue(self.repository.delete(profile.id))
        self.assertFalse(self.repository.delete(profile.id))
        self.assertIsNone(self.repository.get(profile.id))


if __name__ == "__main__":
    unittest.main()
