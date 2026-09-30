"""Web Server CLI 参数测试。"""

import pytest

from app.cli import build_parser


def test_cli_uses_defaults_without_workspace_argument() -> None:
    args = build_parser().parse_args([])

    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.frontend_dist is None


def test_cli_rejects_removed_workspace_argument() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--workspace", "/tmp/project"])
