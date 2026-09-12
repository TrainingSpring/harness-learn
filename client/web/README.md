# Harness Web 客户端

该目录包含本地 Web API 和 React 客户端。首期只支持固定角色的 1v1 会话，
服务默认监听 `127.0.0.1`，没有身份认证，不应直接暴露到公网。

## 开发环境

在仓库根目录安装 Server 依赖：

```bash
./.venv/bin/pip install -e 'client/web/server[test]'
```

启动 API，并显式指定 Agent workspace：

```bash
cd client/web/server
../../../.venv/bin/python -m app.cli --workspace ../../..
```

另开终端启动前端：

```bash
cd client/web/front
npm install
npm run dev
```

Vite 会把 `/api` 代理到 `http://127.0.0.1:8765`。

## 测试与构建

```bash
cd client/web/server
../../../.venv/bin/pytest

cd ../front
npm test
npm run typecheck
npm run build
```

生产构建完成后，可由 FastAPI 同源托管：

```bash
cd client/web/server
../../../.venv/bin/python -m app.cli \
  --workspace ../../.. \
  --frontend-dist ../front/dist
```

当前活动 Run 和待确认权限保存在 Server 进程内。刷新页面可以恢复已写入
SQLite 的消息，但服务重启后不能恢复尚未处理的权限弹窗。
