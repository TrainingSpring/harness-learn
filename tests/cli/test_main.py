import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "code"))

from cli.main import build_runtime  # noqa: E402


def test_build_runtime_creates_session_scoped_context():
    runtime, context = build_runtime()

    assert runtime.context is context
    assert runtime.ctx.session_id == context.sid
    assert [tool["name"] for tool in runtime.tools.list] == ["read", "write"]
