"""持久化实体 ID 生成规则测试。"""

import re
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from storage.ids import generate_id  # noqa: E402


class PersistentIdTests(unittest.TestCase):
    """验证持久化实体使用可迁移的语义化随机 ID。"""

    def test_agent_id_uses_prefix_and_uppercase_random_part(self):
        """Agent ID 必须符合 agent_ 加十位大写字母/数字的格式。"""
        entity_id = generate_id("agent")

        self.assertRegex(entity_id, r"^agent_[A-Z0-9]{10}$")

    def test_different_entity_types_have_their_own_prefix(self):
        """不同实体类型的 ID 前缀必须可区分。"""
        self.assertTrue(generate_id("llm").startswith("llm_"))
        self.assertTrue(generate_id("session").startswith("session_"))
        self.assertTrue(generate_id("participant").startswith("participant_"))

    def test_unknown_prefix_is_rejected(self):
        """未知实体类型不能生成没有约束的 ID。"""
        with self.assertRaises(ValueError):
            generate_id("unknown")

    def test_generated_ids_are_not_sequential(self):
        """连续生成的 ID 不应暴露自增序号。"""
        first = generate_id("agent")
        second = generate_id("agent")

        self.assertNotEqual(first, second)
        self.assertIsNone(re.fullmatch(r"agent_\\d+", first))


if __name__ == "__main__":
    unittest.main()
