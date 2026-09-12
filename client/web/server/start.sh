#!/usr/bin/env bash

# 以严格模式启动 Harness 本地 Web API。
# 脚本按自身位置定位仓库根目录，因此不要求必须先 cd 到特定目录。
set -euo pipefail

SERVER_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SERVER_DIR/../../.." && pwd)"

PYTHON_BIN="${HARNESS_PYTHON:-$PROJECT_ROOT/.venv/bin/python}"
WORKSPACE="${HARNESS_WORKSPACE:-$PROJECT_ROOT}"
HOST="${HARNESS_HOST:-127.0.0.1}"
PORT="${HARNESS_PORT:-8765}"
FRONTEND_DIST="${HARNESS_FRONTEND_DIST:-}"

usage() {
  cat <<'EOF'
用法：
  ./start.sh [选项]

选项：
  --workspace PATH       Agent 工作目录，默认为仓库根目录
  --host HOST            监听地址，默认为 127.0.0.1
  --port PORT            监听端口，默认为 8765
  --frontend-dist PATH   可选的前端 dist 目录，用于同源托管
  -h, --help             显示帮助

环境变量：
  HARNESS_PYTHON HARNESS_WORKSPACE HARNESS_HOST HARNESS_PORT HARNESS_FRONTEND_DIST
EOF
}

while (($# > 0)); do
  case "$1" in
    --workspace)
      [[ $# -ge 2 ]] || { echo "--workspace 需要路径参数" >&2; exit 2; }
      WORKSPACE="$2"
      shift 2
      ;;
    --host)
      [[ $# -ge 2 ]] || { echo "--host 需要地址参数" >&2; exit 2; }
      HOST="$2"
      shift 2
      ;;
    --port)
      [[ $# -ge 2 ]] || { echo "--port 需要端口参数" >&2; exit 2; }
      PORT="$2"
      shift 2
      ;;
    --frontend-dist)
      [[ $# -ge 2 ]] || { echo "--frontend-dist 需要路径参数" >&2; exit 2; }
      FRONTEND_DIST="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知选项：$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python 虚拟环境不存在或不可执行：$PYTHON_BIN" >&2
  echo "请先创建 .venv，或通过 HARNESS_PYTHON 指定 Python 路径。" >&2
  exit 1
fi

if [[ ! -d "$WORKSPACE" ]]; then
  echo "Agent workspace 不存在：$WORKSPACE" >&2
  exit 1
fi

if [[ -n "$FRONTEND_DIST" && ! -d "$FRONTEND_DIST" ]]; then
  echo "前端 dist 目录不存在：$FRONTEND_DIST" >&2
  exit 1
fi

cd "$SERVER_DIR"

SERVER_ARGS=(
  --workspace "$WORKSPACE"
  --host "$HOST"
  --port "$PORT"
)
if [[ -n "$FRONTEND_DIST" ]]; then
  SERVER_ARGS+=(--frontend-dist "$FRONTEND_DIST")
fi

echo "启动 Harness Web API: http://$HOST:$PORT"
echo "Agent workspace: $WORKSPACE"

# exec 让 Ctrl+C 和退出码直接传递给 Uvicorn，避免额外留下壳进程。
exec "$PYTHON_BIN" -m app.cli "${SERVER_ARGS[@]}"
