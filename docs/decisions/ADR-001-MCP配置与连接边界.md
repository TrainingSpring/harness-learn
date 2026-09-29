# ADR-001：MCP 配置与运行时连接边界

## 状态

已接受

## 日期

2026-09-28

## 背景

MCP Server 配置既需要由 Harness 的 UI 修改，也需要允许用户直接编辑配置文件。
同时，同一个 MCP Server 可能被多个 Agent 和多个 Session 使用，但每个 Session 的
协议请求、连接状态、订阅和上下文必须隔离。

如果把 Server 配置放入 SQLite 或让配置对象携带运行时连接，会产生两个问题：

1. 外部编辑渠道和 Web UI 会出现两套配置来源。
2. 持久化数据会混入子进程、HTTP session、请求 ID 等短生命周期对象。

## 决策

### 1. MCP Server 主配置使用 JSON 文件

唯一配置文件为：

```text
~/harness-learn/mcp/config.json
```

`code/agent/mcp/config_store.py` 独立负责读取、校验、原子写入和 revision 冲突检测。
该模块不依赖 SQLite、FastAPI、Session 或 Agent。

### 2. 本地和远程配置使用判别类型

每个 Server 必须具有 `is_local` 字段：

- `is_local: true`：当前阶段使用 `stdio`，包含 command、args、directory、env 等本地字段；directory 是 MCP 服务自身的启动目录，不是 Session workspace。
- `is_local: false`：使用 `streamable_http`，包含 URL、headers、auth_mode 等远程字段。

两种配置不能混用字段；连接状态、PID、工具快照和临时授权状态不写入 JSON。

### 3. MCP Server 注册表保持只读和无缓存

`McpServerRegistry` 只根据 `McpConfigStore` 的最新快照完成列举、按 ID 查询、启用状态
检查和 Agent 引用校验。它不保存运行时连接，也不主动启动 Server。

### 4. Agent/Session/Runtime 不在配置阶段耦合

阶段 0-1 不修改 AgentProfile、AgentFactory、Session 或 Runtime。后续 Agent 只保存
`mcp_server_ids`；Session/Agent 创建运行时 MCP Client；Runtime 只消费内部 Tool 和事件。

### 5. stdio 连接按 Session 隔离

单条 stdio 的 stdin/stdout 只能绑定一个 MCP Client，不能直接被多个 Session 共享。后续
本地生命周期管理可以管理同一 Server 的多个本地实例，但不得把一条协议流复用给不同 Session。

## 被否决的方案

### MCP Server 配置存入 SQLite

否决原因：不满足用户直接编辑配置的需求，并且会让 MCP Server 配置和 Agent/Session 状态
产生不必要的数据库耦合。

### 在 Agent 中保存 MCP Tool 列表

否决原因：Tool 列表是 Server 运行时发现结果，不是 Agent 的稳定配置；当前只按整个 Server
分配能力。

### 由 Runtime 直接读取 config.json 或调用 MCP Client

否决原因：Runtime 只负责 Agent Loop。配置读取、协议连接和能力适配属于 MCP 模块，避免
Runtime 依赖文件格式和外部协议。

## 后果

- UI 和外部编辑器都可以维护同一个配置文件。
- 配置 Store 可以单独测试，也可以在非 Web 场景复用。
- API 层需要处理文件冲突和敏感字段掩码。
- 后续 Session 连接管理需要明确区分“配置级本地实例”和“Session 级 MCP Client”。
