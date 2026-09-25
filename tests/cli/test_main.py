import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "code"))

from cli.main import build_agent  # noqa: E402


def test_build_agent_creates_session_scoped_context():
    agent = build_agent()

    assert agent.runtime.context is agent.context
    assert agent.execution_context.session_id == agent.context.session_id
    assert [tool["name"] for tool in agent.tools.list] == ["read", "write"]
