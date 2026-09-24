"""Session 权限规则恢复和隔离的集成测试。"""

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "code" / "agent"))

from permission.PermissionManager import PermissionManager  # noqa: E402
from permission.policies import ProtectedResourcePolicy  # noqa: E402
from permission.types import (  # noqa: E402
    PermissionAction,
    PermissionDecision,
    PermissionMode,
    PermissionRequest,
    PermissionScope,
)
from storage.database import StateDatabase  # noqa: E402
from storage.repositories.session import SessionRepository  # noqa: E402
from storage.repositories.session_permission_rule import (  # noqa: E402
    SessionPermissionRuleRepository,
)


class PermissionPersistenceTests(unittest.TestCase):
    """验证 Session 规则的持久化、重开和隔离。"""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = StateDatabase(self.temp_dir.name)
        self.database.initialize()
        self.project = Path(self.temp_dir.name) / "project"
        self.project.mkdir()
        self.sessions = SessionRepository(self.database)
        self.rules = SessionPermissionRuleRepository(self.database)
        self.session = self.sessions.create("DIRECT")
        self.sessions.update_project_path_before_first_message(
            self.session.id,
            str(self.project),
        )
        self.sessions.update_permission_mode(self.session.id, PermissionMode.BUILD.value)

    def tearDown(self) -> None:
        self.database.close()
        self.temp_dir.cleanup()

    def _manager(self, session_id: str) -> PermissionManager:
        session = self.sessions.get(session_id)
        assert session is not None
        return PermissionManager(
            mode=PermissionMode(session.permission_mode),
            session_id=session.id,
            project_path=session.project_path,
            rule_repository=self.rules,
            protected_resource_policy=ProtectedResourcePolicy(["/system"]),
        )

    def _request(self, session_id: str, call_id: str = "call_001") -> PermissionRequest:
        return PermissionRequest(
            action=PermissionAction.FILE_WRITE,
            resource="/outside/src/app.py",
            tool_name="write",
            call_id=call_id,
            session_id=session_id,
        )

    def test_session_rule_survives_manager_recreation(self) -> None:
        request = self._request(self.session.id)
        self._manager(self.session.id).grant(
            request,
            scope=PermissionScope.SESSION,
            resource="/outside/src",
        )

        recreated = self._manager(self.session.id)
        self.assertEqual(
            recreated.check(self._request(self.session.id, "call_002")),
            PermissionDecision.ALLOW,
        )

    def test_session_rules_are_not_visible_to_another_session(self) -> None:
        request = self._request(self.session.id)
        self._manager(self.session.id).deny(
            request,
            scope=PermissionScope.SESSION,
            resource="/outside/src",
        )
        other = self.sessions.create("DIRECT")
        self.sessions.update_project_path_before_first_message(other.id, str(self.project))
        self.sessions.update_permission_mode(other.id, PermissionMode.BUILD.value)

        self.assertEqual(
            self._manager(other.id).check(self._request(other.id)),
            PermissionDecision.ASK,
        )

    def test_once_rules_are_not_persisted(self) -> None:
        request = self._request(self.session.id)
        self.assertIsNone(
            self._manager(self.session.id).grant(
                request,
                scope=PermissionScope.ONCE,
                resource=str(self.project / "src"),
            )
        )

        self.assertEqual(self.rules.list_for_session(self.session.id), [])


if __name__ == "__main__":
    unittest.main()
