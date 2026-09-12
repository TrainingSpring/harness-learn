"""本地 Web Server 的命令行启动入口。"""

import argparse
from pathlib import Path

import uvicorn

from .config import WebServerSettings
from .main import create_app


def build_parser() -> argparse.ArgumentParser:
    """定义显式 workspace、监听地址和静态构建参数。"""
    parser = argparse.ArgumentParser(description="启动 Harness 本地 Web 服务")
    parser.add_argument("--workspace", required=True, type=Path, help="Agent 工作目录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument("--port", default=8765, type=int, help="监听端口")
    parser.add_argument(
        "--frontend-dist",
        type=Path,
        default=None,
        help="可选的前端 dist 目录",
    )
    return parser


def main() -> None:
    """校验启动参数并以单 worker 运行 Uvicorn。"""
    args = build_parser().parse_args()
    settings = WebServerSettings(
        workspace=args.workspace,
        host=args.host,
        port=args.port,
        frontend_dist=args.frontend_dist,
    )
    # RunRegistry 只存在当前进程，首期明确固定一个 worker。
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        workers=1,
    )


if __name__ == "__main__":
    main()

