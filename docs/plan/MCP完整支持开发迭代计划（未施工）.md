# MCP 完整支持开发迭代计划（未施工）

> 状态：未施工。
>
> 本计划根据当前产品设定重新收口。MCP Server 注册配置由用户可编辑的
> `~/harness-learn/mcp/config.json` 管理；SQLite 只保存 Agent 对 MCP Server 的引用，
> 不保存 MCP Server 主配置。当前只支持把整个 MCP Server 分配给 Agent，不支持把一个
> Server 内的单个 Tool 分配给 Agent。

## 1. 目标和最终边界

完成后，用户可以：

1. 在设置中查看所有已经注册的 MCP Server。
2. 通过新增、编辑、删除维护 MCP Server 配置。
3. 使用本地 MCP Server 和远程 MCP Server。
4. 对本地 MCP Server 执行启动、停止、重启；远程 MCP Server 不显示这些操作。
5. 在创建或编辑 Agent 时选择多个 MCP Server。
6. 让不同 Agent 拥有不同的 MCP Server 集合。
7. 创建 Session 后，由该 Session 的 Agent 使用自己配置的 MCP Server。
8. 自动完成 MCP 初始化、版本协商、能力协商和能力发现。
9. 将 MCP Server 的 Tools 映射为当前 Agent 的动态 Tools，复用现有 Agent Loop、
   Context、PermissionManager 和运行事件链路。
10. 支持 MCP Resources、Resource Templates、Prompts、Roots、Logging、Progress、
    Cancellation、Sampling、Elicitation、Completions 和列表变更通知。
11. 支持本地 stdio 和远程 Streamable HTTP；协议扩展不得破坏没有 MCP 的 Agent。
12. 在设置页、角色编辑页和会话页中显示可诊断的 MCP 状态、来源和错误。

最终职责边界：

```text
config.json
  └── MCP Server 注册配置

AgentProfile / Agent
  └── mcp_server_ids: 选择了哪些 MCP Server

Session
  └── 为当前 Agent 创建 MCP Client 连接和会话级协议状态

MCP Client / Adapter
  └── MCP 协议、能力发现、Tools/Resources/Prompts 转换

Runtime
  └── 继续负责 Agent Loop，不实现 MCP JSON-RPC 细节
```

## 2. 明确不做的事情

以下内容不进入本计划的产品契约：

1. 不新增 `mcp_servers` SQLite 表保存 MCP Server 主配置。
2. 不新增 `agent_mcp_servers` 关联表来替代 Agent 配置字段；Agent 只保存有序的
   `mcp_server_ids` 列表，具体落地字段沿用当前 AgentProfile 的持久化方式。
3. 不支持 MCP Tool 级分配，不增加 `mcpToolPolicy`、Tool 白名单或 Tool 黑名单 UI。
4. 不允许远程 MCP Server 由 Harness 启动、停止或重启。
5. 不把 MCP Server 的 Tools 复制到全局内置 `ToolCatalog`。Tools 只在当前 Agent
   连接成功后动态注册，Agent 销毁时注销。
6. 不把 MCP Resource 列表或 Server instructions 自动写成系统消息。
7. 不将远程 Server 返回的文本、描述或 Prompt 当成可信系统指令。
8. 不把连接对象、子进程句柄、HTTP Session、工具快照写入 `config.json`。
9. 不因为设置页刷新而改变 Agent 当前已经运行的连接；刷新只重新读取配置和刷新管理状态。

## 3. 当前实现映射和改造原则

当前项目已有：

- `Agent`：持有 LLM、Context、Tools、Skills、Permission 和 Runtime 的完整运行对象。
- `Runtime`：负责 Agent Loop、模型调用、工具调用、权限暂停/恢复和运行事件。
- `Tools`：负责工具注册、参数解析、权限前置检查、执行和结果编码。
- `AgentProfile` / `AgentProfileRepository`：负责 Agent 的持久化配置。
- `AgentFactory`：根据 AgentProfile、LLM、Tools、Skills、Context 创建 Agent。
- `SessionExecution`：创建或恢复 Session，并向 Agent 提供 Session Context。
- `PermissionManager`：按 Session 权限模式和权限规则处理权限请求。
- `SkillProfile` / `SkillSet`：提供 Skill 的元数据和当前轮指令。
- Web 设置页和角色编辑页：已经有 LLM、Tool、Skill 的管理和选择流程。

改造原则：

1. `Agent` 继续是独立可执行对象；MCP 作为 Agent 的一项可选能力，不把 MCP 逻辑塞进
   Runtime。
2. `AgentFactory` 只负责根据 `mcp_server_ids` 装配能力，不负责实现 JSON-RPC。
3. MCP Server 配置读取由独立 `McpConfigStore` 负责，不复用 SQLite Repository。
4. API 和 UI 只提交 Server ID，不提交 Server 当前发现到的 Tool ID 列表。
5. 所有来自 MCP Server 的数据都按不可信外部数据处理，先校验、限长、脱敏，再进入
   Agent、Context 或前端。

## 4. 配置文件契约

### 4.1 文件位置和写入约定

固定路径：

```text
~/harness-learn/mcp/config.json
```

实现中使用 `Path.home() / "harness-learn" / "mcp" / "config.json"` 计算路径，不能改为隐藏目录
或项目目录下的其他路径。目录不存在时由 `McpConfigStore` 创建。

配置文件要求：

- UTF-8 JSON。
- 顶层结构稳定，当前版本为 `version: 1`。
- 写入采用临时文件、flush、fsync、原子替换。
- 写入前校验完整文档，不能把半截 JSON 写入正式文件。
- 文件被外部程序修改后，下一次列表读取或用户点击刷新时重新读取。
- UI 写入时检查文件版本或内容摘要，避免覆盖用户刚从编辑器保存的外部修改；发生冲突返回
  `MCP_CONFIG_CONFLICT`，由用户重新读取后再提交。
- 文件权限在支持的平台上尽量限制为当前用户可读写；日志和 API 响应不得输出敏感值。
- 不在配置文件中保存连接状态、子进程 PID、工具发现快照或临时 OAuth state。

### 4.2 顶层结构

```json
{
  "version": 1,
  "servers": [
    {
      "id": "mcp_filesystem",
      "name": "Filesystem",
      "description": "本地文件能力",
      "is_local": true,
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"],
      "cwd": null,
      "env": {},
      "enabled": true
    },
    {
      "id": "mcp_remote",
      "name": "Remote Service",
      "description": "远程 MCP 服务",
      "is_local": false,
      "transport": "streamable_http",
      "url": "https://example.com/mcp",
      "headers": {},
      "auth_mode": "none",
      "enabled": true
    }
  ]
}
```

### 4.3 配置字段

公共字段：

| 字段 | 类型 | 备注 |
|---|---|---|
| `id` | `string` | 稳定唯一 ID；由服务端生成或保留已有 ID，不能因为编辑名称而改变 |
| `name` | `string` | 用户可见名称；不能为空 |
| `description` | `string` | 可选说明，作为 UI 元数据，不作为系统指令 |
| `is_local` | `boolean` | 必填；`true` 表示 Harness 管理本地启动，`false` 表示远程连接 |
| `transport` | `string` | 当前支持 `stdio`、`streamable_http` |
| `enabled` | `boolean` | 是否允许 Agent 新建连接；禁用不等于删除 |

本地配置（`is_local: true`）：

| 字段 | 类型 | 备注 |
|---|---|---|
| `transport` | `"stdio"` 或本地 HTTP 类型 | stdio 是当前必须支持的本地方式 |
| `command` | `string` | 启动命令；与 `args` 分离执行，禁止 shell 拼接 |
| `args` | `string[]` | 参数数组，保留参数边界 |
| `cwd` | `string \| null` | 子进程工作目录；启动前规范化并校验 |
| `env` | `object` | 子进程环境变量；敏感值在日志中脱敏 |
| `startup_timeout_ms` | `integer` | 可选，启动超时 |
| `shutdown_timeout_ms` | `integer` | 可选，停止超时 |

远程配置（`is_local: false`）：

| 字段 | 类型 | 备注 |
|---|---|---|
| `transport` | `"streamable_http"` | 远程 MCP 连接方式 |
| `url` | `string` | MCP endpoint；只允许配置的协议和安全重定向策略 |
| `headers` | `object` | 静态请求头；敏感值读取和返回时掩码 |
| `auth_mode` | `string` | `none`、`bearer`、`oauth` 等受支持模式 |
| `request_timeout_ms` | `integer` | 可选，请求超时 |

`is_local` 和 `transport` 是判别字段。后端必须拒绝本地配置缺少 `command`、远程配置缺少
`url`、本地带远程专用字段或远程带本地启动字段的文档，避免“所有字段可选”的不可维护模型。

### 4.4 Agent 配置字段

在现有 `AgentProfile` 增加：

```python
mcp_server_ids: list[str] = field(default_factory=list)
```

字段含义：

- 保存 Agent 拥有的 MCP Server ID，顺序表示暴露给 Agent 的稳定顺序。
- 保存前去重，保留第一次出现的顺序。
- 只允许引用 `config.json` 中存在且结构有效的 Server。
- Server 被禁用时不删除 Agent 引用；重新启用后可恢复使用。
- 删除 Server 时必须先清理或阻止所有 Agent 引用，不能留下悬空 ID。
- 不保存 MCP Tool ID、工具快照、连接状态或授权 Token。

这样做的原因是：MCP Server 的来源是可外部编辑的配置文件，而 Agent 的“拥有哪些能力”
属于 Agent 自身配置。二者分离后，刷新 `config.json` 不会重写整个 Agent，也不会把外部
Server 配置复制出多份。

## 5. 运行时对象和连接边界

### 5.1 对象职责

```text
McpConfigStore
  读取、校验、写回 config.json

McpServerRegistry
  根据 ID 查询当前有效配置，检测外部变更

LocalMcpServerManager
  启动、停止、重启、查询本地 MCP 实例

McpTransport
  只负责 JSON-RPC 双向传输、请求关联、通知、超时和取消

McpClient
  负责 initialize、能力协商、tools/resources/prompts 等协议方法

McpConnectionManager
  为 Agent/Session 创建和关闭 MCP Client 连接

McpToolAdapter / McpResourceProvider / McpPromptProvider
  把 MCP 能力转换成 Harness 内部能力

Agent
  持有当前 Agent 的 MCP 能力集合，并在销毁时关闭连接

Runtime
  只消费内部 Tool、Context 和运行事件，不了解 MCP JSON-RPC
```

### 5.2 Agent 和 Session 的装配

装配流程：

```text
Session 创建/恢复
    ↓
读取 AgentProfile.mcp_server_ids
    ↓
McpConfigStore 根据 ID 读取有效配置
    ↓
McpConnectionManager 为当前 Agent/Session 建立 Client
    ↓
initialize + capability discovery
    ↓
McpToolAdapter 注册动态 Tools
McpResourceProvider / McpPromptProvider 保存能力
    ↓
Agent 交给 Runtime 执行 Agent Loop
```

Agent 本身仍然是独立对象，拥有 LLM、Context、Tools、Skills、Permission、Runtime 和 MCP
能力。Runtime 不负责读取配置文件，不负责启停 MCP，不负责直接调用 MCP Client。

### 5.3 本地进程和连接隔离

本地 `stdio` 的一条 stdin/stdout 通道只能对应一个协议 Client，不能把同一条流同时当成
多个独立 Session 的连接。因此：

- `LocalMcpServerManager` 按 `server_id` 管理本地活动实例集合，而不是假设一个 stdio
  进程可以被任意数量的 Client 共享。
- Agent/Session 默认按连接需要创建自己的 stdio 子进程和 MCP Client 状态。
- 设置页的“启动”表示允许并预启动该 Server 的本地托管实例；“停止”停止该 Server 的
  所有活动本地实例；“重启”先停止后重新启动。
- 停止或重启期间，新建连接必须得到稳定的 `MCP_SERVER_STARTING` / `MCP_SERVER_STOPPED`
  状态，不能悄悄复用失效流。
- 如果未来本地 Server 使用可多客户端访问的 HTTP transport，则 Manager 可以管理一个
  HTTP 进程，Agent 通过各自的 HTTP Client 连接；这不改变 Agent 连接状态隔离。
- 不同 Session 不共享 Context、授权状态、请求 ID、订阅和 MCP Client；只允许在进程层面
  按 transport 能力受控复用。

## 6. MCP 协议范围

### 6.1 必须实现的基础协议

- JSON-RPC 2.0 request、response、notification 和 error。
- `initialize`、协议版本协商、client/server capabilities、`notifications/initialized`。
- `ping`、关闭、请求 ID 管理、并发请求、超时和取消。
- stdio framing、stderr 隔离、子进程退出和异常恢复。
- Streamable HTTP POST、SSE、`Mcp-Session-Id`、`MCP-Protocol-Version`、断线重连。
- 版本不兼容、能力缺失、响应格式错误、请求超时和远端 401/403 的稳定错误。

### 6.2 Server 能力

支持并进行能力协商：

- Tools：`tools/list`、分页、`tools/call`、`listChanged`。
- Resources：`resources/list`、`resources/read`、订阅、模板和变更通知。
- Prompts：`prompts/list`、`prompts/get`、参数补全和变更通知。
- Logging、Completions、Experimental 扩展。

### 6.3 Client 能力

支持并按 Session 注入：

- Roots：当前 workspace 和用户已授权的根目录。
- Sampling：Server 请求当前 Agent LLM 进行采样。
- Elicitation：Server 请求用户提供结构化或 URL 输入。
- 日志、进度、取消、列表变更通知和实验性能力。

所有扩展能力必须经过 capability 检查；Server 没有声明能力时，不能直接调用对应方法。

## 7. 工具、资源和 Prompt 的内部映射

### 7.1 MCP Tools

每个已发现的远端 Tool 映射为当前 Agent 的动态 Tool，但只在当前 Agent 生命周期内有效：

```text
mcp__{server_id}__{remote_tool_name}
```

绑定对象至少包含：

```python
McpToolBinding(
    internal_name: str,
    server_id: str,
    remote_name: str,
    description: str,
    input_schema: dict,
    output_schema: dict | None,
)
```

要求：

- Server ID 和 Tool 名称都要经过规范化，冲突时返回诊断错误而不是覆盖内置 Tool。
- `inputSchema`、`outputSchema` 和 annotations 必须校验后再交给模型。
- 参数对象、嵌套深度、字符串、数组和 JSON 总大小有限制。
- MCP Tool 调用先构造内部 PermissionRequest，再进入现有 PermissionManager。
- `plan/build/yolo` 只由 Session 权限策略决定；MCP Server 自己的 annotations 不能提升权限。
- text、image、audio、resource_link、embedded resource、structuredContent 转为受限的
  ToolResult/Attachment。
- Tool 列表变化时只替换当前 Server 的动态绑定，不修改内置 ToolCatalog。
- 当前版本不提供 MCP Tool 选择器；Agent 绑定了 Server 后，默认获得该 Server 暴露的全部
  有效 Tools，单 Tool 分配留待未来独立设计。

### 7.2 MCP Resources

Resource 不是普通 Tool 的别名，使用独立 Provider：

- 列表、分页、模板、读取、订阅和更新通知。
- URI scheme、host、路径、MIME、来源和大小校验。
- 文件 URI 必须同时受 Roots、Session workspace 和 PermissionManager 约束。
- 用户或模型明确请求后才能读取；`resources/list` 不自动把资源内容放入 Context。
- Context 默认记录资源引用、摘要和来源，完整原文只在当前请求确实需要时进入模型输入。

### 7.3 MCP Prompts

- 列表、分页、读取、参数校验、补全和变更通知。
- Prompt message 的角色、文本、图片和资源内容转换为内部临时输入。
- MCP Prompt 不是 Skill，不是系统 Prompt，不自动注入每轮输入。
- Server 返回内容不能覆盖系统规则、权限规则或 Agent 身份。
- 是否写入 Context 按一次性用户操作处理，不能隐式写成系统消息。

## 8. 权限、Context 和安全边界

### 8.1 权限

MCP Tool、Resource、Server 连接、Sampling、Elicitation 都走当前 PermissionManager。至少
定义以下内部动作：

- `mcp.server.connect`
- `mcp.tool.call`
- `mcp.resource.read`
- `mcp.sampling.request`
- `mcp.elicitation.request`

具体是否询问由 Session 权限模式和风险信息决定：

- `plan`：MCP 只读能力可以读取，但不能产生写入性副作用；无法可靠判断时请求权限。
- `build`：默认允许工作目录内的低风险能力，工作目录外或有外部副作用的 MCP 调用请求权限。
- `yolo`：默认允许，仍受强制黑名单、协议安全校验、资源大小和传输安全限制。

MCP Server 的描述、Tool annotations、Prompt 内容不能绕过上述规则。

### 8.2 Context

- Tool call、Tool result、权限请求、连接状态和错误按现有运行事件/消息协议进入 Context。
- Resource 内容只在明确读取后进入当前模型输入；默认存引用/摘要，避免污染历史上下文。
- Prompt 作为一次临时输入，不默认成为系统上下文。
- Sampling 请求只发送 Server 明确要求的最小 messages、system prompt 和 model preferences，
  不默认暴露完整 Session Context。
- 外部 Server instructions 标记为不可信元数据，不能替换 Agent 的系统指令。

### 8.3 安全

- stdio 的 command 和 args 分离传递，禁止 shell 拼接。
- 本地 `cwd`、环境变量和命令路径经过规范化及策略校验。
- 远程 URL 限制 scheme、重定向、私网访问和 DNS rebinding，防止 SSRF。
- Token/header/env 中的敏感值不写日志、不进入普通 API 响应、不进入 Context。
- 配置文件中的敏感字段返回掩码值；编辑时支持保留原值而不是强制回传明文。
- Tool/Resource/Prompt 结果都有单项、总响应、附件、嵌套深度和超时上限。
- 未确认完成状态的有副作用调用不得在重启后自动重放。
- MCP Server 的文本可能包含提示注入，必须当作外部数据而非系统指令。

## 9. 代码目录和文件变更计划

### 9.1 新增 `code/agent/mcp/`

```text
code/agent/mcp/
├── __init__.py
├── types.py                 # 配置、状态、能力和 DTO 的内部类型
├── config.py                # config.json 路径和 Local/Remote 判别联合类型
├── config_store.py          # 读取、校验、刷新、原子写入、版本冲突检测
├── registry.py              # Server ID 查询、enabled 校验和外部修改检测
├── process_manager.py       # 本地 Server 启停、重启、状态和实例注册
├── protocol.py              # JSON-RPC request/response/notification/error
├── validation.py            # 外部消息、Schema、URI 和大小校验
├── transport.py             # Transport 抽象、请求关联、通知、超时、取消
├── stdio_transport.py       # 本地 subprocess、stdin/stdout、stderr、退出处理
├── http_transport.py        # Streamable HTTP、SSE、session id、重连
├── oauth.py                 # HTTP 授权发现、PKCE、token 刷新和撤销
├── lifecycle.py             # initialize、版本、capability、ping、shutdown
├── capabilities.py          # Client/Server 能力模型和协商结果
├── client.py                # MCP Client 协议方法
├── connection_manager.py    # Agent/Session 连接生命周期
├── pagination.py            # cursor 分页
├── notifications.py         # tools/resources/prompts/logging/progress 通知
├── tools.py                 # MCP Tool binding 和 Tool Adapter
├── resources.py             # Resource、Template、读取和订阅
├── prompts.py               # Prompt、参数和消息转换
├── roots.py                 # workspace roots 和 roots/list_changed
├── sampling.py              # Server -> Client sampling 桥接
├── elicitation.py           # Server -> Client 用户输入桥接
├── logging.py               # MCP 日志脱敏、限长和等级
└── errors.py                # 稳定异常和错误码
```

### 9.2 核心后端修改

| 文件 | 修改 | 原因 |
|---|---|---|
| `code/agent/storage/types.py` | `AgentProfile` 增加 `mcp_server_ids` | 记录 Agent 选择的 Server，不复制 Server 配置 |
| `code/agent/storage/repositories/agent_profile.py` | 读写 `mcp_server_ids` | 让创建、编辑、恢复 Agent 时保持选择结果 |
| `code/agent/storage/migrations.py` | 给 Agent 配置增加 JSON 字段或等价迁移 | 持久化 Agent 的 Server ID 列表，不建 MCP Server 表 |
| `code/agent/runtime/agent_factory.py` | 从配置文件解析 Server 并装配 MCP 能力 | Factory 负责组装，不实现协议 |
| `code/agent/runtime/agent.py` | 持有 MCP capability set 和关闭钩子 | Agent 是完整能力对象 |
| `code/agent/runtime/runtime.py` | 只接收统一 ToolResult/运行事件 | 保持 Runtime 与 MCP 协议解耦 |
| `code/agent/session/session_service.py` | 创建/恢复时建立 MCP 连接，关闭时释放 | 连接状态属于运行时 Session，不属于持久化配置 |
| `code/agent/session/ExecutionContext.py` | 提供 workspace、session_id、agent_id 给 Roots/权限 | MCP 必须服从当前 Session 边界 |
| `code/agent/tools/types.py` | 增加外部来源和 MCP binding 元数据 | 让 UI、事件和权限知道 Tool 来源 |
| `code/agent/tools/tools.py` | 支持当前 Agent 动态注册/注销 MCP Tools | 不污染全局内置 ToolCatalog |
| `code/agent/permission/types.py`、`PermissionManager.py`、`policies.py` | 增加 MCP 动作和风险描述 | MCP 调用必须走现有 Session 权限链路 |
| `code/agent/context/context.py` | 增加 MCP 事件/资源引用的统一编码 | 不把 MCP 原始 JSON-RPC 直接塞进 Context |

### 9.3 后端 API 修改和新增

新增或拆分 `client/web/server/app/api/mcp.py`，通过依赖注入提供 `McpConfigStore`、
`McpServerRegistry` 和 `LocalMcpServerManager`。

设置 API：

```text
GET    /api/settings/mcp
POST   /api/settings/mcp
GET    /api/settings/mcp/{server_id}
PATCH  /api/settings/mcp/{server_id}
DELETE /api/settings/mcp/{server_id}

POST   /api/settings/mcp/{server_id}/start
POST   /api/settings/mcp/{server_id}/stop
POST   /api/settings/mcp/{server_id}/restart
GET    /api/settings/mcp/{server_id}/status
POST   /api/settings/mcp/{server_id}/refresh
POST   /api/settings/mcp/{server_id}/test
```

接口规则：

- 列表和详情从 `config.json` 读取最新配置，并补充内存中的运行状态。
- `POST/PATCH/DELETE` 写回 `config.json`，不写 MCP Server SQLite 表。
- `start/stop/restart` 只允许 `is_local=true`；远程请求返回
  `MCP_REMOTE_LIFECYCLE_UNSUPPORTED`。
- 删除本地 Server 前读取运行状态；运行中先停止，停止成功后再删除配置。
- 停止失败时删除失败，避免配置消失但进程仍在运行。
- 删除前检查 Agent 引用；可选择返回引用列表并要求用户确认，最终不能留下悬空 ID。
- `refresh` 重新读取外部文件并返回配置摘要；不替换当前运行 Agent 的连接。
- `test` 对本地启动临时测试实例，对远程建立短连接；测试结束关闭临时连接。
- 所有错误使用统一结构 `{ error: { code, message, details } }`，不暴露 command、Token、
  Authorization header 或完整环境变量。

Agent API 扩展：

```json
{
  "mcpServerIds": ["mcp_filesystem", "mcp_remote"]
}
```

创建和编辑 Agent 时：

- 只校验 Server ID 存在、配置有效、没有重复。
- 禁用 Server 可以保存引用，但新建 Session 时提示不可用。
- 不接受 `mcpToolPolicy`、Tool ID 或完整 Tool 定义。
- Agent 列表和详情返回 `mcpServers` 的 Server ID，必要时附带名称摘要。

运行事件 DTO：

- `mcp_connection_status`
- `mcp_capabilities_changed`
- `mcp_tool_call`
- `mcp_resource_read`
- `mcp_progress`
- `mcp_log`
- `mcp_elicitation_required`
- `mcp_sampling_required`

原始 JSON-RPC 不直接透传到前端。

## 10. Web UI 计划

### 10.1 设置页 MCP 列表

新增：

```text
client/web/front/src/features/settings/pages/McpSettingsPage.tsx
client/web/front/src/features/settings/components/CreateMcpDialog.tsx
client/web/front/src/features/settings/components/DeleteMcpDialog.tsx
client/web/front/src/features/settings/components/McpStatusBadge.tsx
client/web/front/src/features/settings/api.ts
```

修改：

```text
client/web/front/src/features/settings/components/SettingsNav.tsx
client/web/front/src/features/settings/pages/SettingsLayout.tsx
client/web/front/src/api/types.ts
client/web/front/src/features/settings/api.ts
```

列表内容：

- 名称、描述、本地/远程、transport、启用状态、运行状态。
- 当前协议版本、Server 信息和能力摘要。
- 顶部“新增”和刷新按钮。
- 每行提供编辑、删除。
- `is_local=true` 显示启动、停止、重启；根据当前状态禁用不适用按钮。
- `is_local=false` 不显示启动、停止、重启，只显示测试连接、刷新能力等连接操作。
- 本地服务删除时显示“运行中将先停止”的影响提示；停止失败时保留配置。

新增/编辑 Modal：

- 先选择本地或远程，再显示对应字段。
- 本地填写 command、args、cwd、env、超时。
- 远程填写 URL、headers、认证模式、超时。
- 保存前展示字段校验错误，不允许把本地和远程字段混合提交。
- 敏感字段显示掩码；未修改时提交“保留原值”，不能因为 UI 回显掩码而覆盖真实值。
- 不显示或编辑 MCP Tool 分配选项。

### 10.2 Agent 创建/编辑中的 MCP 选择

在现有角色创建/编辑弹窗中新增“已配置 MCP”字段，交互复用当前 Skills 的独立弹窗模式：

新增：

```text
client/web/front/src/features/agents/components/McpServerPickerDialog.tsx
```

修改：

```text
client/web/front/src/features/agents/components/CreateAgentDialog.tsx
client/web/front/src/features/agents/api.ts
client/web/front/src/api/types.ts
```

交互要求：

- 点击按钮打开 MCP Server 列表弹窗，不在 Agent 表单中铺开大量选项。
- 支持搜索、复选、多选、确认和取消。
- 每项显示名称、本地/远程、transport、启用状态、运行状态。
- 编辑角色时回显 `mcpServerIds`。
- 只保存 Server ID；不显示 Tool 级复选框。
- Server 被禁用、配置无效或已被外部删除时，显示明确状态并阻止提交无效引用。
- 创建 Agent 不自动启动远程 Server；Session 真正使用时按配置连接。

### 10.3 会话页

- 在会话环境中显示当前 Agent 已装配的 MCP Server 和连接状态。
- MCP Tool 调用显示 Server 名称、Tool 名称、参数摘要和权限状态。
- Progress 更新同一状态项，不重复生成消息。
- Resource 读取显示 URI、来源、大小和结果状态。
- Elicitation/Sampling 显示来源 Server、等待状态和用户操作入口。
- 连接失败只影响对应 Agent/Session，并显示重试或刷新配置入口。

## 11. 实施阶段

所有阶段初始状态均为“未施工”。每个阶段完成后必须在本文档更新状态、实际文件、测试命令
和验收结果。

### 阶段 0：契约冻结和现状清理（已完成）

**目标**：在写协议代码前固定文件格式、职责边界和错误语义。

**修改/新增**：

- 本计划文档：冻结 `config.json` 路径、`is_local`、本地/远程字段和 Agent 关联规则。
- `docs/adr/`：记录 MCP Server 配置不入 SQLite、Agent 只保存 Server ID、Runtime 不实现
  MCP 协议、本地 stdio 连接隔离四项决策。
- 检查当前代码中是否已有 MCP 残留的 SQLite 表、Repository 或 API，并列出迁移/删除项。

**原因**：先消除旧计划中 SQLite Server 表和 Tool 级策略，避免后续实现走错边界。

**验收**：计划、ADR、错误码和接口命名一致，没有同时存在两套 MCP Server 配置来源。

**完成记录（2026-09-28）**：

- 新增 `docs/decisions/ADR-001-MCP配置与连接边界.md`。
- 冻结 `~/harness-learn/mcp/config.json`、`is_local` 判别类型、Agent 只保存 Server ID、
  Runtime 不依赖 MCP 协议四项边界。
- 明确阶段 0-1 不修改 Agent、Session、Runtime 和 SQLite。

### 阶段 1：配置模型和 `config.json` Store（已完成）

**目标**：能可靠读取、校验、刷新和原子写入本地 MCP 注册配置。

**新增/修改**：

- `code/agent/mcp/types.py`
- `code/agent/mcp/config.py`
- `code/agent/mcp/config_store.py`
- `code/agent/mcp/registry.py`
- `code/agent/mcp/errors.py`
- 当前应用启动入口：创建默认目录和 Store 依赖

**实现内容**：

- `McpConfigDocument`、`LocalMcpServerConfig`、`RemoteMcpServerConfig` 使用判别联合。
- 校验 `version`、Server ID 唯一性、公共字段、`is_local` 和 transport 专属字段。
- 支持空配置文件和首次启动自动创建。
- 支持外部修改检测、文件摘要、原子写入和版本冲突。
- 对未知字段给出兼容策略：保留可扩展 metadata，拒绝会改变语义的错误字段。

**验收**：本地/远程配置能分别读写；错误 JSON 不会破坏旧配置；外部编辑后刷新可看到变化；
并发写入不会静默覆盖。

**完成记录（2026-09-28）**：

- 新增 `code/agent/mcp/types.py`、`config_store.py`、`registry.py`、`errors.py` 和包入口。
- 实现本地 `stdio`、远程 `streamable_http` 判别配置。
- 实现首次创建、严格字段校验、稳定 ID、原子写入、SHA-256 revision 冲突检测。
- 实现 Registry 的列举、按 ID 查询、启用校验和 Agent Server ID 去重保序校验。
- 新增 `tests/mcp/` 下 8 个配置与注册表测试。
- 应用启动接线暂未加入，留到设置 API 阶段，避免产生没有消费者的全局服务依赖。

### 阶段 2：Agent MCP 引用持久化（已完成）

**目标**：Agent 能保存多个 MCP Server ID，且不保存 MCP Server 主配置。

**修改**：

- `code/agent/storage/types.py`
- `code/agent/storage/migrations.py`
- `code/agent/storage/repositories/agent_profile.py`
- Agent API schema 和序列化代码
- Agent 相关测试

**实现内容**：

- 增加 `AgentProfile.mcp_server_ids`。
- 按现有 Agent 配置风格增加数据库 JSON 字段或等价持久化字段。
- 读写时去重、保序并校验 ID 格式。
- 删除 MCP Server 时检查 Agent 引用，禁止悬空引用。
- 不新增 `mcp_servers` 或 `agent_mcp_servers` 表。

**验收**：创建、编辑、读取、恢复 Agent 后 MCP Server ID 不丢失；同一 Agent 绑定多个 Server；
没有任何 Tool ID 或连接对象进入 AgentProfile。

**完成记录（2026-09-28）**：

- `AgentProfile` 新增 `mcp_server_ids`，在领域层校验 MCP Server ID 并去重保序。
- schema 迁移至 v8，在 `agent_profiles.mcp_server_ids_json` 持久化该引用列表；未新增 MCP 相关 SQLite 表。
- Agent 创建、更新和读取 API 支持 `mcpServerIds`，仅允许引用当前 `McpServerRegistry` 中存在的 Server；禁用 Server 的引用仍允许保存。
- Web 应用服务容器注入 `McpServerRegistry`，但 Agent、Session、Runtime 不依赖 Store 或配置文件实现。
- 增加存储与 API 回归测试，覆盖读写去重、已注册 Server 和未知 Server 的拒绝。

### 阶段 3：JSON-RPC 和 Transport（已完成）

**目标**：完成可测试的双向 MCP 消息层。

**新增**：

- `protocol.py`
- `validation.py`
- `transport.py`
- `stdio_transport.py`
- `http_transport.py`

**实现内容**：

- JSON-RPC request、response、notification、error 和 ID 关联。
- stdio 使用 argv 启动，stdout 只处理协议消息，stderr 独立收集。
- 子进程退出、启动/停止超时、优雅关闭和强制终止。
- Streamable HTTP POST、SSE、Session ID、协议头、断线重连和 404 重新初始化。
- 每个请求支持超时、取消和最大响应限制。
- 禁止 Shell 拼接、禁止把原始错误和敏感 header 直接返回前端。

**验收**：fake stdio/HTTP Server 能覆盖并发请求、通知、超时、取消、断线、畸形响应和退出。

**完成记录（2026-09-28）**：

- 新增 `protocol.py`，提供严格 JSON-RPC 2.0 request、response、notification、error 模型、ID 关联和 JSON 编码。
- 新增 `transport.py`，定义不包含生命周期逻辑的同步 Transport 接口。
- 新增 `stdio_transport.py`，使用 argv + `shell=False` 启动子进程；stdout 独占协议消息，stderr 独立有界收集；支持并发请求、通知回调、超时、取消、大小限制、优雅关闭和强制终止。
- 新增 `http_transport.py`，支持 Streamable HTTP 的 JSON/SSE 响应、`Mcp-Session-Id`、协议版本头、超时、取消、响应大小限制和 404 会话过期信号。
- Transport 不负责 `initialize`、能力发现、重连策略或 Tool 映射；404 只清理失效 Session ID 并交给后续 Client 生命周期层重新初始化。
- 新增 8 个协议与 Transport 回归测试，覆盖并发响应、通知、超时、取消、SSE、会话失效、畸形响应和服务退出。

### 阶段 4：本地服务生命周期（未施工）

**目标**：设置页和运行时可以可靠控制本地 MCP 服务。

**新增**：

- `code/agent/mcp/process_manager.py`
- 本地状态模型和状态事件

**实现内容**：

- `start(server_id)`、`stop(server_id)`、`restart(server_id)`、`status(server_id)`。
- 只接受 `is_local=true`；远程调用返回稳定错误。
- 启动时建立实例记录，停止时等待退出，超时后强制终止并记录失败。
- 删除流程必须是“读取配置 -> 检查本地 -> 停止运行实例 -> 停止成功 -> 删除配置”。
- 服务状态只保存在运行时内存/诊断事件，不写回 `config.json` 作为事实状态。
- 不把 stdio 的单流错误地共享给多个独立 Session。

**验收**：启动、停止、重启状态可查询；停止失败阻止删除；远程服务没有生命周期按钮；
服务异常退出有可诊断原因。

### 阶段 5：Lifecycle、Capabilities 和 MCP Client（未施工）

**目标**：能建立 MCP Client 并完成初始化、版本和能力发现。

**新增**：

- `lifecycle.py`
- `capabilities.py`
- `client.py`
- `connection_manager.py`
- `pagination.py`
- `notifications.py`

**实现内容**：

- initialize/version negotiation/initialized/ping/shutdown。
- 发现 Server capabilities 和 instructions。
- tools/resources/prompts/completions 的分页和 listChanged。
- 每个 Agent/Session 的连接状态、重连和释放。
- Session 关闭、取消、Agent 重建时关闭连接。

**验收**：版本不兼容、初始化超时、能力缺失、Server 主动断开都能得到稳定状态；两个
Session 使用同一个 Server 时请求 ID、订阅、Context 和连接状态互不影响。

### 阶段 6：Tools 动态映射、权限和 Runtime 接入（未施工）

**目标**：MCP Tool 能被当前 Agent 使用，同时不改变 Runtime 的职责。

**修改/新增**：

- `code/agent/mcp/tools.py`
- `code/agent/tools/types.py`
- `code/agent/tools/tools.py`
- `code/agent/runtime/agent.py`
- `code/agent/runtime/agent_factory.py`
- `code/agent/runtime/runtime.py`
- `code/agent/permission/*`
- `code/agent/context/context.py`

**实现内容**：

- tools/list 分页、动态注册、listChanged 原子替换和注销。
- namespace、同名检测、Schema 校验和结果转换。
- MCP Tool 统一走 Session 权限；不新增 Agent 独立权限模式。
- Tool call、result、permission、error 转为现有运行事件和 Context 项。
- Runtime 只处理内部 Tool 调用结果，不调用 `McpClient.call_tool`。

**验收**：模型能调用 MCP Tool；权限行为符合 Session 的 plan/build/yolo；MCP Tool 不能
覆盖内置 Tool，不能扩大权限，不能因为 Server 描述而改变系统规则。

### 阶段 7：Resources、Roots、Prompts 和 Completions（未施工）

**目标**：完整处理 MCP 的非 Tool 能力，并保持 Context 边界。

**新增**：

- `resources.py`
- `roots.py`
- `prompts.py`
- 相关 Context/事件转换代码

**实现内容**：

- Resources、Templates、读取、订阅和更新通知。
- Roots 由当前 Session workspace 和授权根目录生成。
- Prompts、参数校验、消息转换和 completions。
- 资源只在明确请求后读取；Prompt 不自动作为系统消息。

**验收**：资源和 Prompt 能被明确使用；未经请求不会自动进入 Context；文件资源仍服从
Session workspace、Roots 和 PermissionManager。

### 阶段 8：Logging、Progress、Cancellation、Sampling、Elicitation（未施工）

**目标**：完成 Server -> Client 的交互能力和用户可见运行状态。

**新增**：

- `logging.py`
- `sampling.py`
- `elicitation.py`
- 运行事件映射和前端 DTO

**实现内容**：

- 日志分级、脱敏、限长、折叠展示。
- Progress 映射为可更新状态，不重复生成消息。
- 用户取消/超时/关闭连接时发送 cancellation notification。
- Sampling 只发送 Server 明确需要的最小内容，并单独请求权限。
- Elicitation 进入前端结构化交互，支持确认、拒绝、取消、超时。

**验收**：上述事件不阻塞无关 Session；敏感输入不进入普通日志；Sampling 不默认发送
完整 Context；Elicitation 有明确来源和用户操作。

### 阶段 9：远程认证和安全收口（未施工）

**目标**：完成 Streamable HTTP 的认证、授权和安全策略。

**新增/修改**：

- `oauth.py`
- `config.py` 的 auth 字段校验
- 前后端授权状态 API
- 安全测试和敏感信息脱敏测试

**实现内容**：

- 401 metadata、授权服务器发现、动态注册或手工 Client ID。
- Authorization Code + PKCE、state、redirect URI、resource indicator。
- Token 过期刷新、撤销和删除。
- Token 不进入 URL、日志、Context 或非目标 Server 请求。
- UI 只显示授权状态和过期时间，不回显完整 Token。

**验收**：认证成功、失败、过期、撤销、state mismatch、错误 audience 和重定向攻击均有
稳定处理和测试。

### 阶段 10：MCP 设置页（未施工）

**目标**：用户可以完全通过 UI 管理 `config.json` 中的 MCP Server。

**修改/新增**：

- `client/web/server/app/api/mcp.py`
- `client/web/server/app/schemas/mcp.py`
- `client/web/server/app/dependencies.py`
- `client/web/front/src/api/types.ts`
- `client/web/front/src/features/settings/api.ts`
- `client/web/front/src/features/settings/pages/McpSettingsPage.tsx`
- `client/web/front/src/features/settings/components/CreateMcpDialog.tsx`
- `client/web/front/src/features/settings/components/DeleteMcpDialog.tsx`
- `client/web/front/src/features/settings/components/McpStatusBadge.tsx`
- 设置导航和路由文件

**实现内容**：

- 列表读取 config.json，显示本地/远程和状态。
- 新增、编辑写入 config.json；删除执行本地停止保护。
- 刷新重新读取外部修改。
- 本地显示启动/停止/重启；远程隐藏这些按钮。
- 本地/远程 Modal 使用不同字段，保存前严格校验。
- 显示测试连接、能力刷新和诊断摘要。

**验收**：用户可以完成“新增本地 -> 启动 -> 停止 -> 编辑 -> 重启 -> 删除”和“新增远程
-> 测试/刷新 -> 编辑 -> 删除”；外部编辑 config.json 后刷新可见；UI 不显示 Tool 分配项。

### 阶段 11：Agent MCP 选择和会话端到端收口（未施工）

**目标**：用户可以把已注册 Server 分配给不同 Agent，并在会话中实际使用。

**修改/新增**：

- `client/web/server/app/api/agents.py`
- `client/web/server/app/schemas/agent.py`
- `client/web/front/src/features/agents/components/CreateAgentDialog.tsx`
- `client/web/front/src/features/agents/components/McpServerPickerDialog.tsx`
- Agent API client、类型和测试
- Session 运行事件和会话页展示

**实现内容**：

- 角色创建/编辑增加 MCP Server 选择弹窗。
- 支持搜索、多选、确认、取消、编辑回显和禁用状态提示。
- 保存 `mcpServerIds`，不保存 Tool ID。
- AgentFactory 依据这些 ID 装配 MCP。
- 会话页显示连接、工具调用、权限、资源、进度和失败状态。

**验收**：两个 Agent 可以拥有不同 MCP 集合；创建 Session 后分别建立正确连接；模型能在
权限允许时调用对应 Server；编辑 Agent 后重新创建 Session 能看到新配置；没有选择 MCP 的
Agent 完全保持原有行为。

### 阶段 12：完整测试、兼容性和文档收口（未施工）

**目标**：确认完整 MCP 支持不会破坏现有 Agent、Session、Tools、Skills 和权限功能。

**测试范围**：

- 配置文件：首次创建、空文件、错误 JSON、外部修改、并发写入、原子替换。
- 模型：本地/远程判别、字段互斥、ID、启用状态和悬空 Agent 引用。
- 进程：跨平台路径、启动、停止、重启、退出、超时、信号和 stderr。
- 协议：JSON-RPC 并发、分页、通知、取消、断线和版本协商。
- Agent：多 Server、空 Server、禁用 Server、恢复、连接释放和重复绑定。
- 权限：plan/build/yolo、MCP Tool/Resource/Connect/Sampling/Elicitation。
- UI：本地/远程字段、按钮显示、删除保护、刷新、编辑回显、选择弹窗。
- 安全：命令注入、SSRF、路径穿越、提示注入、Token 泄露、资源耗尽。
- 回归：没有 MCP 配置时，现有 read/write/edit/bash/process、Skills、Session 和 Agent
  流程行为不变。

**验收**：后端测试、前端测试、类型检查、构建和跨平台相关测试通过；文档中的实际文件、
错误码、接口和最终行为与代码一致，计划才允许标记为已完成。

## 12. 错误码约定

至少定义以下稳定错误码：

| 错误码 | 含义 |
|---|---|
| `MCP_CONFIG_NOT_FOUND` | 配置文件不存在且无法创建 |
| `MCP_CONFIG_INVALID` | 配置 JSON 或字段结构无效 |
| `MCP_CONFIG_CONFLICT` | 外部修改导致写入版本冲突 |
| `MCP_SERVER_NOT_FOUND` | Server ID 不存在 |
| `MCP_SERVER_DISABLED` | Server 被禁用 |
| `MCP_SERVER_NOT_LOCAL` | 对远程 Server 调用了本地生命周期操作 |
| `MCP_REMOTE_LIFECYCLE_UNSUPPORTED` | 远程服务不支持 Harness 启停重启 |
| `MCP_SERVER_START_FAILED` | 本地服务启动失败 |
| `MCP_SERVER_STOP_FAILED` | 本地服务停止失败 |
| `MCP_SERVER_ALREADY_RUNNING` | 本地服务已经运行 |
| `MCP_SERVER_STOPPED` | 服务当前已停止 |
| `MCP_PROTOCOL_UNSUPPORTED` | 协议版本不兼容 |
| `MCP_CONNECTION_FAILED` | 建立连接失败 |
| `MCP_CAPABILITY_UNAVAILABLE` | Server 未声明所需能力 |
| `MCP_AGENT_REFERENCE_CONFLICT` | 删除 Server 时仍有 Agent 引用 |
| `MCP_TOOL_INVALID` | Tool 描述或 Schema 无效 |
| `MCP_PERMISSION_REQUIRED` | MCP 操作需要 Session 权限确认 |
| `MCP_EXTERNAL_DATA_LIMIT` | 外部参数、结果或资源超过限制 |
| `MCP_AUTH_REQUIRED` | 远程 Server 需要用户授权 |
| `MCP_AUTH_FAILED` | 远程授权失败 |

## 13. 风险和处理

| 风险 | 影响 | 处理 |
|---|---|---|
| 用户手工修改 config.json | UI 覆盖外部修改 | 读取摘要、原子写入、冲突检测和刷新 |
| stdio 被多个 Session 共享 | 请求和响应错配、上下文泄露 | 每个 Agent/Session 保持独立 MCP Client/流 |
| 本地命令不可信 | 任意代码执行 | argv 启动、cwd/命令策略、明确展示和用户控制 |
| 远程 MCP 不可用 | Agent 等待或失败 | 超时、取消、重连退避和降级状态 |
| Server Tool 提示注入 | 模型越权或改变规则 | 外部数据标记、系统规则优先、权限独立判断 |
| MCP Tool 覆盖内置 Tool | 核心能力被替换 | 强制 namespace 和同名拒绝 |
| 删除运行中本地 Server | 残留进程或配置丢失 | 先停止，停止失败则拒绝删除 |
| Server 被 Agent 引用后删除 | Session 恢复失败 | 删除前检查引用并要求清理/确认 |
| 大型资源/结果耗尽 Context | Token、内存和 UI 压力 | 分页、限长、摘要、附件限制和响应上限 |
| OAuth/headers 泄露 | 凭据泄露 | 掩码、脱敏、Audience 绑定和不进 Context |

## 14. 最终产品形态

### 14.1 设置 MCP

用户进入设置中的 MCP 页面：

1. 页面从 `~/harness-learn/mcp/config.json` 读取并展示所有 Server。
2. 点击新增，选择本地或远程，填写对应配置并保存到 JSON 文件。
3. 本地 Server 行显示启动、停止、重启；远程 Server 行不显示这些操作。
4. 点击编辑修改 JSON 中对应配置；外部编辑后点击刷新即可同步列表。
5. 删除本地运行中的 Server 时，系统先停止其所有活动实例，成功后再删除配置。
6. 删除失败或配置冲突时保留原文件，并向用户说明原因。

### 14.2 角色配置

用户创建或编辑 Agent：

1. 打开 MCP 选择弹窗。
2. 从当前 config.json 已注册的 Server 中搜索和多选。
3. 保存后 AgentProfile 只保存 Server ID 列表。
4. 不需要也不能在这里选择 MCP Server 内部的 Tool。
5. 不同 Agent 可以绑定不同的 MCP Server 集合。

### 14.3 会话运行

1. Session 创建该 Agent，并根据 `mcp_server_ids` 装配 MCP Client。
2. 本地 Server 按 transport 创建本地实例，远程 Server 建立 HTTP 连接。
3. MCP Client 完成初始化和能力发现后，当前 Agent 获得动态 Tools、Resources 和 Prompts。
4. 模型调用 MCP Tool 时，复用 Session 权限模式和权限请求流程。
5. 工具结果、资源引用、连接状态、进度和错误进入统一 Context/运行事件。
6. Session 结束时释放连接；不影响其他 Session 的 Context、请求和订阅。

## 15. 计划完成定义

只有同时满足以下条件，本文档才能从“未施工”改为“已完成”：

- MCP Server 主配置唯一存储在 `~/harness-learn/mcp/config.json`，没有 SQLite Server 主表。
- 配置支持外部编辑、刷新、原子写入和冲突保护。
- 本地/远程通过 `is_local` 和 transport 正确区分，配置字段不混用。
- 本地 Server 可以启动、停止、重启；远程 Server 不显示或执行本地生命周期操作。
- 删除本地运行 Server 时必须先停止，停止失败不能删除。
- Agent 可以保存多个 MCP Server ID，不保存 MCP Tool 分配规则。
- 不同 Agent 可以拥有不同 MCP Server 集合，且没有 MCP 的 Agent 行为不变。
- stdio、Streamable HTTP、JSON-RPC、初始化、能力协商、分页、通知、取消和错误恢复可用。
- MCP Tools、Resources、Prompts、Roots、Logging、Progress、Sampling、Elicitation 和
  Completions 有明确实现、权限和 Context 边界。
- MCP Tool 完全复用现有 Tools、Runtime、Context 和 PermissionManager，不绕过 Session 权限。
- 设置页 MCP 列表、增删改、刷新、状态控制和本地删除保护完整可用。
- Agent 创建/编辑支持 MCP Server 弹窗多选、回显和保存。
- Token、headers、环境变量和外部敏感输入不会进入日志、普通 API 响应或 Context。
- Windows、macOS、Linux 的路径和本地进程行为通过测试。
- 前后端测试、类型检查、构建、回归和安全测试通过。
