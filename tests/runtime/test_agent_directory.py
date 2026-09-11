"""AgentDirectory 的 Agent 发现与加入资格测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from runtime.agent_directory import AgentDirectory  # noqa: E402
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.agent_profile import AgentProfileRepository  # noqa: E402
from storage.repositories.llm_profile import LLMProfileRepository  # noqa: E402
from storage.types import AgentProfile, LLMProfile  # noqa: E402


class AgentDirectoryTests(unittest.TestCase):
    """验证用户选择 Agent 所需的发现和启用状态判断。"""

    def setUp(self):
        """创建两个启用 Agent 和一个停用 Agent。"""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        LLMProfileRepository(self.database).save(
            LLMProfile(
                id="llm_7KQ2M8P4XZ",
                name="通用模型",
                provider="openai",
                base_url=None,
                model="gpt-5",
                credential_ref="env:OPENAI_API_KEY",
            )
        )
        repository = AgentProfileRepository(self.database)
        for agent_id, name, expertise, enabled in (
            ("agent_1V3ASAXQ2A", "代码专家", ["Python"], True),
            ("agent_9U3M7BKP2C", "测试专家", ["pytest"], True),
            ("agent_8LRT3N5QYB", "停用专家", ["Python"], False),
        ):
            repository.save(
                AgentProfile(
                    id=agent_id,
                    name=name,
                    description="开发工作",
                    personality="务实",
                    expertise=expertise,
                    llm_profile_id="llm_7KQ2M8P4XZ",
                    tools=["read"],
                    permission_mode="BUILD",
                    is_enabled=enabled,
                )
            )
        self.directory = AgentDirectory(repository)

    def tearDown(self):
        """关闭数据库并清理临时目录。"""
        self.database.close()
        self.temp_dir.cleanup()

    def test_list_enabled_and_filter_by_expertise(self):
        """目录只返回启用 Agent，并支持按专业标签筛选。"""
        self.assertEqual(
            [profile.name for profile in self.directory.list(expertise="pytest")],
            ["测试专家"],
        )
        self.assertNotIn(
            "停用专家",
            [profile.name for profile in self.directory.list()],
        )

    def test_can_join_requires_an_enabled_agent(self):
        """只有存在且启用的 Agent 才能加入会话。"""
        self.assertTrue(self.directory.can_join("agent_1V3ASAXQ2A"))
        self.assertFalse(self.directory.can_join("agent_8LRT3N5QYB"))
        self.assertFalse(self.directory.can_join("agent_7KQ2M8P4XZ"))


if __name__ == "__main__":
    unittest.main()
