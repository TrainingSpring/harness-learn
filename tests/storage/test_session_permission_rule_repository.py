"""SessionPermissionRuleRepository 的 SQLite 集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[2] / "code" / "agent"))

from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionRule,
)
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.repositories.session_permission_rule import (  # noqa: E402
    SessionPermissionRuleRepository,
)


class SessionPermissionRuleRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.sessions = SessionRepository(self.database)
        self.repository = SessionPermissionRuleRepository(self.database)
        self.project = Path(self.temp_dir.name) / "project"
        self.project.mkdir()
        self.session = self.sessions.create("DIRECT")
        self.sessions.update_project_path_before_first_message(
            self.session.id,
            str(self.project),
        )

    def tearDown(self):
        self.database.close()
        self.temp_dir.cleanup()

    def test_rules_are_persisted_per_session_and_rehydrated_from_project_root(self):
        rule = PermissionRule(
            action=PermissionAction.FILE_WRITE,
            resource=str(self.project / "src"),
            decision=PermissionDecision.ALLOW,
            session_id=self.session.id,
        )

        self.repository.save(rule)

        loaded = self.repository.list_for_session(self.session.id)
        self.assertEqual(loaded, [rule])

    def test_rules_are_not_visible_to_other_session(self):
        other = self.sessions.create("DIRECT")
        self.repository.save(
            PermissionRule(
                action=PermissionAction.BASH_EXECUTE,
                resource=None,
                decision=PermissionDecision.DENY,
                session_id=self.session.id,
            )
        )

        self.assertEqual(self.repository.list_for_session(other.id), [])

    def test_external_file_rule_is_persisted_and_rehydrated(self):
        rule = PermissionRule(
            action=PermissionAction.FILE_READ,
            resource="/outside/project.txt",
            decision=PermissionDecision.ALLOW,
            session_id=self.session.id,
        )

        self.repository.save(rule)

        self.assertEqual(self.repository.list_for_session(self.session.id), [rule])


if __name__ == "__main__":
    unittest.main()
