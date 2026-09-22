"""AgentProfileRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.database import StateDatabase  # noqa: E402
from storage.errors import StorageConflictError  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class AgentProfileRepositoryTests(unittest.TestCase):
    """验证 Agent 配置的持久化和查询语义。"""

    def setUp(self):
        """为每个测试创建独立数据库和依赖的 LLM 配置。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.llm_repository = LLMProfileRepository(self.database)
        self.repository = AgentProfileRepository(self.database)
        self.llm_repository.save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="代码模型",
                provider="openai",
                base_url="https://api.openai.com/v1",
                model="gpt-5",
                api_key="sk-test-key",
            )
        )

    def tearDown(self):
        """关闭连接并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def make_profile(
        self,
        profile_id="agent_1V3ASAXQ2A",
        name="代码专家",
        expertise=None,
        is_enabled=True,
    ):
        """创建测试用 AgentProfile。"""
        return AgentProfile(
            id=profile_id,
            name=name,
            description="负责实现和修改代码",
            personality="务实",
            expertise=expertise or ["Python", "代码实现"],
            llm_profile_id="llm_7KQ2M8P4XZ",
            tools=["read", "write"],
            is_enabled=is_enabled,
        )

    def test_save_and_get_round_trip_preserves_agent_configuration(self):
        """保存后读取应还原 Agent 描述、能力和工具集合。"""
        profile = self.repository.save(self.make_profile())

        loaded = self.repository.get(profile.id)

        self.assertEqual(loaded.name, "代码专家")
        self.assertEqual(loaded.expertise, ["Python", "代码实现"])
        self.assertEqual(loaded.tools, ["read", "write"])
        self.assertFalse(hasattr(loaded, "permission_mode"))
        self.assertIsNotNone(loaded.created_at)

    def test_list_enabled_can_filter_by_expertise(self):
        """列表接口只返回启用 Agent，并支持擅长领域筛选。"""
        self.repository.save(self.make_profile())
        self.repository.save(
            self.make_profile(
                profile_id="agent_8LRT3N5QYB",
                name="测试专家",
                expertise=["pytest"],
            )
        )
        self.repository.save(
            self.make_profile(
                profile_id="agent_9U3M7BKP2C",
                name="停用专家",
                is_enabled=False,
            )
        )

        profiles = self.repository.list_enabled(
            limit=10,
            offset=0,
            expertise="pytest",
        )

        self.assertEqual([profile.name for profile in profiles], ["测试专家"])

    def test_save_updates_existing_profile_without_changing_id(self):
        """相同 Agent ID 保存时应更新配置。"""
        self.repository.save(self.make_profile())
        self.repository.save(self.make_profile(name="更新后的代码专家"))

        loaded = self.repository.get("agent_1V3ASAXQ2A")
        self.assertEqual(loaded.name, "更新后的代码专家")
        self.assertEqual(len(self.repository.list_enabled(10, 0)), 1)

    def test_missing_llm_reference_is_a_storage_conflict(self):
        """Agent 引用不存在的 LLM 时不能写入孤立配置。"""
        profile = self.make_profile()
        profile.llm_profile_id = "llm_8LRT3N5QYB"

        with self.assertRaises(StorageConflictError):
            self.repository.save(profile)

    def test_delete_returns_whether_profile_existed(self):
        """删除存在的 Agent 返回 True，重复删除返回 False。"""
        self.repository.save(self.make_profile())

        self.assertTrue(self.repository.delete("agent_1V3ASAXQ2A"))
        self.assertFalse(self.repository.delete("agent_1V3ASAXQ2A"))
        self.assertIsNone(self.repository.get("agent_1V3ASAXQ2A"))


if __name__ == "__main__":
    unittest.main()
