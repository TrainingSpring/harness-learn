# Web 客户端开发计划

## 计划目标

本计划在现有 Python Agent 核心之外增加首个可视化客户端，用于验证已经完成的 Agent 配置、会话持久化、上下文恢复、工具调用和权限暂停/恢复流程。

首期产品范围：

- 只提供 Web 客户端，不实现 Desktop 和 CLI 客户端。
- 只提供固定角色的 1v1 会话，不在 UI 中开放 GROUP 群聊。
- 左侧栏上部提供“新对话”和“角色”入口。
- 左侧栏中部展示历史会话。
- 左侧栏底部提供设置入口。
- 右侧内容区承载新会话、对话、角色列表和设置页面。
- 设置页首期提供主题切换、LLM 配置列表和工具列表。
- LLM 与工具首期只展示，不在 Web 中编辑，避免 UI 开发同时扩大配置写入和凭据管理范围。
- Agent 工具触发 ASK 权限时，Web 必须显示确认界面并能恢复原有 Runtime。

本期不实现：

- 多 Agent 群聊调度。
- Agent 委托和 Agent 自由对话。
- 用户登录、远程访问和多用户隔离。
- LLM 配置、Agent 配置和工具代码的 Web 编辑。
- Desktop 打包、PWA 离线运行和云同步。
- 浏览器刷新后恢复一个尚未处理的权限弹窗。

## 产品与视觉方向

### 设计原则

界面参考 Codex 的工作台结构，但不复制品牌视觉。整体应安静、简约、有科技感，重点服务长时间阅读、角色切换和反复执行任务，而不是做成营销网站。

- 第一屏直接进入工作台，不增加欢迎页或宣传 Hero。
- 信息层级主要依靠布局、字重、边框和留白，不使用大面积渐变和装饰光球。
- 颜色使用中性灰作为界面基础，配合低饱和青绿色作为选中和交互强调色，并用琥珀色、红色表达提醒和危险状态。
- 卡片圆角不超过 8px；页面区块不做悬浮大卡片，只为角色条目、列表项和权限弹窗使用卡片边界。
- 工具按钮优先使用 `lucide-react` 图标；不手绘 SVG。
- 字号使用固定设计令牌，不根据 viewport 宽度缩放。
- 明暗主题都通过 CSS 变量实现，主题选择保存在浏览器 `localStorage`。
- 所有按钮、输入框、菜单和弹窗必须支持键盘操作、可见焦点和无障碍名称。

### 桌面布局

~~~text
┌──────────────────────┬─────────────────────────────────────────────┐
│  新对话              │                                             │
│  角色                │              右侧内容页                     │
│──────────────────────│                                             │
│  今天                │  新会话 / 对话 / 角色列表 / 设置            │
│    会话 A            │                                             │
│    会话 B            │                                             │
│  更早                │                                             │
│    会话 C            │                                             │
│                      │                                             │
│──────────────────────│                                             │
│  设置                │                                             │
└──────────────────────┴─────────────────────────────────────────────┘
~~~

建议尺寸：

- 左侧栏桌面宽度固定为 `264px`，允许在 `240px` 到 `288px` 之间微调。
- 内容区使用 `minmax(0, 1fr)`，避免长代码块撑破布局。
- 对话正文最大宽度约 `860px`，输入区与正文使用同一内容轴。
- 顶部和底部操作区固定，中部会话列表独立滚动。
- 对话输入框固定在内容区底部，消息列表独立滚动。

### 移动端布局

- 小于 `768px` 时左侧栏变为抽屉，由菜单图标打开。
- 内容区始终占满屏幕；打开抽屉时应有遮罩并可按 Escape 关闭。
- 对话输入区考虑 `env(safe-area-inset-bottom)`。
- 角色卡片从多列网格降为单列。
- 权限确认弹窗在窄屏下使用底部面板，但仍保留明确的允许和拒绝按钮。

### 页面状态

每个数据页面必须设计以下状态：

- 初次加载 Skeleton。
- 数据为空的空状态。
- 请求失败状态和重试操作。
- 正常数据状态。
- 提交或流式响应期间的进行中状态。
- 对话被权限请求暂停时的等待确认状态。

## 总体架构

新增目录：

~~~text
client/
  web/
    README.md
    server/
      pyproject.toml
      app/
        __init__.py
        main.py
        config.py
        dependencies.py
        errors.py
        api/
          __init__.py
          router.py
          agents.py
          sessions.py
          runs.py
          settings.py
        schemas/
          __init__.py
          common.py
          agent.py
          session.py
          context.py
          run.py
          settings.py
        services/
          __init__.py
          chat_service.py
          run_registry.py
      tests/
        conftest.py
        test_agents_api.py
        test_sessions_api.py
        test_runs_api.py
        test_settings_api.py
    front/
      package.json
      tsconfig.json
      vite.config.ts
      index.html
      src/
        main.tsx
        app/
          router.tsx
          providers.tsx
        api/
          client.ts
          stream.ts
          types.ts
        layouts/
          AppShell.tsx
          Sidebar.tsx
          MobileSidebar.tsx
        components/
          Button.tsx
          IconButton.tsx
          Dialog.tsx
          EmptyState.tsx
          ErrorState.tsx
          Skeleton.tsx
        features/
          agents/
          sessions/
          chat/
          permissions/
          settings/
        styles/
          tokens.css
          global.css
        test/
          setup.ts
      e2e/
        direct-chat.spec.ts
        navigation.spec.ts
        responsive.spec.ts
~~~

依赖关系：

~~~text
浏览器 UI
  → TypeScript API Client
    → FastAPI 路由与 Pydantic DTO
      → Web Application Service
        → AgentProfileRepository / AgentFactory / SessionService
          → Repository / Runtime / SQLite
~~~

`server` 是 Web 协议适配层，不复制 Agent 业务逻辑。`front` 不访问 SQLite，也不拼装 Python 对象，只使用稳定的 HTTP DTO 和流事件。

## 技术选型

### Server

采用：

- Python 3.12。
- FastAPI：路由、依赖注入和 OpenAPI 文档。
- Pydantic v2：API 输入输出校验。
- Uvicorn：本地 ASGI 服务。
- `sse-starlette` 或 FastAPI `StreamingResponse`：对话事件流。
- pytest + HTTPX：API 集成测试。

选择 FastAPI 的原因：现有业务核心全部是 Python；FastAPI 可以直接调用 `AgentFactory`、`SessionService` 和 Repository，并用 Pydantic 明确隔离内部领域对象和公开 JSON。

服务首期只监听 `127.0.0.1`。开发环境通过 Vite proxy 将 `/api` 转发给 FastAPI，生产构建可由 FastAPI 挂载 `front/dist`，保持同源并避免开放宽泛 CORS。

### Front

采用：

- React 19 + TypeScript。
- Vite：开发服务器和生产构建。
- React Router：内容页路由。
- TanStack Query：列表、详情和失效刷新等服务端状态。
- 原生 `fetch` + `ReadableStream`：读取 POST 请求返回的 SSE 流。
- `react-markdown` + `remark-gfm`：渲染 Agent Markdown 消息。
- `lucide-react`：界面图标。
- Vitest + Testing Library：组件和状态测试。
- Playwright：真实浏览器流程、移动端和视觉检查。

首期不引入 Redux。服务端数据交给 TanStack Query；流式对话、输入框和弹窗状态使用 feature 内部 hook 或局部 Context。

## Server 设计

### 应用启动与依赖

新增 `client/web/server/app/config.py`：

~~~python
class WebServerSettings(BaseSettings):
    workspace: Path
    host: str = "127.0.0.1"
    port: int = 8765
    frontend_dist: Path | None = None
~~~

用途：集中管理 workspace、监听地址和前端构建目录。`workspace` 必须显式提供或由启动命令确定，不能由每个路由分别调用 `os.getcwd()`。

新增 `client/web/server/app/dependencies.py`：

- `get_database()`：返回应用生命周期内唯一的 `StateDatabase`。
- `get_agent_factory()`：返回运行时 Agent 工厂。
- `get_session_service()`：返回 1v1 会话创建服务。
- `get_run_registry()`：返回当前进程的运行实例注册表。

`main.py` 使用 FastAPI lifespan：

1. 根据配置创建并初始化 `StateDatabase`。
2. 创建共享服务并保存到 `app.state`。
3. 注册 `/api` 路由。
4. 应用关闭时停止活动 run 并关闭数据库。
5. 生产模式下挂载静态文件，并将非 `/api` 路由回退到 `index.html`。

### API 公共契约

所有响应使用 camelCase，内部 Python 对象继续保留 snake_case。转换只能发生在 Pydantic schema 层。

列表响应统一为：

~~~json
{
  "items": [],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "hasMore": false
  }
}
~~~

错误响应统一为：

~~~json
{
  "error": {
    "code": "AGENT_NOT_FOUND",
    "message": "Agent 不存在",
    "details": null
  }
}
~~~

状态码约定：

- `400`：JSON、路径或查询参数格式错误。
- `404`：Agent、Session 或 Run 不存在。
- `409`：Session 状态冲突、Run 已在执行或权限响应不匹配。
- `422`：字段格式正确但不满足业务规则。
- `500`：未预期服务端错误；不得向前端返回 traceback、SQL 或凭据。

新增 `errors.py`，将 `ValueError`、`StorageConflictError`、`CredentialResolutionError` 和运行状态错误映射为稳定 API 错误码。不要直接把底层异常文本作为全部公开契约。

### Agent API

新增 `schemas/agent.py`：

~~~text
AgentSummary:
  id, name, description, personality, expertise, tools, isEnabled

AgentDetail:
  AgentSummary 字段 + llmProfileId + permissionMode
~~~

接口：

~~~text
GET /api/agents?limit=20&offset=0&expertise=Python
GET /api/agents/{agentId}
~~~

`GET /api/agents` 只返回启用的 Agent，供角色列表和新会话选择使用。详情接口可以读取指定配置，但对已禁用项返回明确的 `isEnabled=false`。

已采用 `AgentProfileRepository` 作为 Agent 配置的唯一查询路径。`GET /api/agents` 直接调用 `list_enabled()`；SessionService 在创建会话时读取 Profile 并明确区分“不存在”和“已禁用”。不保留仅转发 Repository 的 `AgentDirectory`，避免查询与资格判断出现两条实现路径。

### Session API

新增 `schemas/session.py`：

~~~text
CreateDirectSessionRequest:
  agentId, title?

SessionSummary:
  id, title, conversationMode, status, agent, createdAt, updatedAt

SessionDetail:
  SessionSummary 字段 + messages
~~~

接口：

~~~text
POST /api/sessions
GET  /api/sessions?limit=30&offset=0
GET  /api/sessions/{sessionId}
GET  /api/sessions/{sessionId}/messages?afterSequence=0
~~~

`POST /api/sessions` 首期只接受：

~~~json
{
  "mode": "DIRECT",
  "agentId": "agent_1V3ASAXQ2A",
  "title": null
}
~~~

路由调用 `SessionService.create_direct_session()`，不允许直接调用 `SessionRepository.create()`，确保会话和唯一 Agent 在同一事务中创建。

历史会话列表需要 Agent 名称和最后一条消息摘要。当前 `SessionRepository.list_recent()` 只返回 Session，因此新增查询仓储：

~~~text
code/agent/storage/repositories/session_query.py

SessionQueryRepository:
  list_direct_summaries(limit, offset)
  get_direct_detail(session_id)
~~~

新增只读类型：

~~~text
DirectSessionSummary:
  session, agent_id, agent_name, last_message, last_sequence_no
~~~

使用一次 JOIN 查询 `sessions`、`session_agents`、`agent_profiles` 和最后一条可展示消息，避免 Web 路由对每个 Session 分别查询产生 N+1。

### Context API

新增 `schemas/context.py`：

~~~text
ContextItemResponse:
  id, sequenceNo, kind, authorAgentId, visibility,
  payload, callId, causedByItemId, createdAt
~~~

首期前端主要展示 `USER_MESSAGE` 和 `AGENT_MESSAGE`。工具调用和工具结果仍返回，但前端应将它们渲染成可折叠执行记录，不能当作普通聊天气泡。

接口只返回业务 ContextItem，不返回 OpenAI Responses input 格式。`type=message`、`input_text` 等厂商字段继续限制在 `ContextService.to_responses_input()` 边界内。

### Run 与流式对话 API

浏览器发送消息需要跨越 Python generator，因此新增 `services/chat_service.py`：

~~~text
ChatService:
  start_message(session_id, text) -> Iterator[ServerEvent]
  resolve_permission(run_id, response) -> Iterator[ServerEvent]
  cancel(run_id) -> None
~~~

新增 `services/run_registry.py`：

~~~text
ActiveRun:
  run_id
  session_id
  agent_id
  agent
  state
  created_at

RunRegistry:
  create(session_id, agent_id, agent) -> ActiveRun
  get(run_id) -> ActiveRun | None
  get_for_session(session_id) -> ActiveRun | None
  remove(run_id) -> None
~~~

用途：当前 Runtime 的 `WAITING_PERMISSION`、pending tool call 和剩余调用队列都在内存中。权限确认请求必须找到原来的 Agent/Runtime 对象，不能收到确认后重新 `AgentFactory.load()`。

首期约束：

- 一个 Session 同时只能有一个活动 Run。
- 服务使用单进程 Uvicorn；不能启动多个 worker，否则内存 RunRegistry 无法跨进程共享。
- 普通对话完成后移除 ActiveRun。
- 进入 `WAITING_PERMISSION` 时保留 ActiveRun，直到确认、拒绝、取消或服务关闭。
- 浏览器刷新可以恢复已持久化消息，但首期不能恢复未处理的内存权限请求；UI 必须明确提示该限制。

接口：

~~~text
POST /api/sessions/{sessionId}/messages
POST /api/runs/{runId}/permission
POST /api/runs/{runId}/cancel
~~~

发送消息请求：

~~~json
{
  "text": "请读取 README.md"
}
~~~

`POST /messages` 返回 `text/event-stream`。浏览器通过 POST `fetch()` 读取流，不使用只能发 GET 的原生 EventSource。

流事件统一为：

~~~text
run.started
message.delta
message.completed
tool.started
tool.completed
permission.required
run.completed
run.failed
~~~

每个 SSE `data` 都使用判别字段：

~~~json
{
  "type": "message.delta",
  "runId": "run_...",
  "sessionId": "session_...",
  "data": {
    "text": "正在"
  }
}
~~~

`permission.required` 数据至少包含：

~~~text
callId, toolName, action, resource, allowedScopes
~~~

前端确认请求：

~~~json
{
  "callId": "call_...",
  "decision": "allow",
  "scope": "once"
}
~~~

服务端必须用 RunRegistry 保存的 pending request 验证 callId，不接受前端重新提交 action、resource、agentId 或 sessionId。

### 设置 API

接口：

~~~text
GET /api/settings/llm-profiles?limit=100&offset=0
POST /api/settings/llm-profiles/models
GET /api/settings/llm-profiles/{profileId}/models
GET /api/settings/tools
~~~

LLM 列表 DTO：

~~~text
LLMProfileSummary:
  id, name, provider, baseUrl, model, hasApiKey, options
~~~

接口绝不返回实际 API Key；列表只返回 `hasApiKey` 或“已配置/未配置”状态。创建时提交 `apiKey`，编辑时省略 `apiKey` 表示保留当前值。

工具列表由 `ToolCatalog.list_available()` 生成，DTO 为：

~~~text
ToolSummary:
  name, description, inputSchema, permissionAction
~~~

不要把 Python 函数、模块路径或任意 `permission` 对象序列化给前端，只提取显示所需字段。

主题设置不需要 Server API。首期主题仅属于浏览器偏好，存储在 `localStorage`；未来出现账户同步时再迁移为用户设置。

## Front 设计

### 路由

~~~text
/                         重定向到最近会话；无会话时进入 /new
/new                      新对话页
/sessions/:sessionId      1v1 对话页
/agents                   角色卡片列表
/agents/:agentId          角色详情
/settings                 重定向到 /settings/appearance
/settings/appearance      主题设置
/settings/llms            LLM 列表
/settings/tools           工具列表
~~~

所有路由共享 `AppShell`，切换内容页时左侧栏不重新挂载，保持历史列表滚动位置和移动端抽屉状态。

### AppShell 与左侧栏

新增：

~~~text
layouts/AppShell.tsx
layouts/Sidebar.tsx
layouts/MobileSidebar.tsx
features/sessions/components/SessionHistory.tsx
features/sessions/components/SessionHistoryItem.tsx
~~~

左侧上部：

- “新对话”使用 `SquarePen` 图标和文字。
- “角色”使用 `Users` 图标和文字。
- 当前路由使用背景、左侧强调线或文字颜色表示，不用大面积高饱和填充。

左侧中部：

- 历史会话按“今天、昨天、更早”分组。
- 每项显示会话标题或首条用户消息摘要，以及 Agent 名称。
- 当前会话保持选中状态。
- 长标题单行省略，完整标题通过 tooltip 提供。
- 首期不实现删除、重命名和搜索，避免引入尚未设计的写接口。

左侧底部：

- “设置”使用 `Settings` 图标。
- 当前主题可使用太阳/月亮图标作为状态提示，但主题修改放在设置页，不在侧栏堆叠额外按钮。

### 新对话页

新增：

~~~text
features/chat/pages/NewChatPage.tsx
features/agents/components/AgentPicker.tsx
features/agents/components/AgentPickerItem.tsx
~~~

进入 `/new` 后，右侧显示会话工作区而不是弹窗：

- 顶部标题为“新对话”。
- 中部显示紧凑角色选择列表，包含名称、描述、性格和 expertise 标签。
- 选中角色后显示输入区。
- 用户发送第一条消息时先调用 `POST /api/sessions`，成功后跳转到 `/sessions/{id}` 并立即开始流式发送。

采用“首次发送时创建 Session”，而不是点击角色就创建，避免用户反复浏览角色时产生大量空会话。

### 角色页面

新增：

~~~text
features/agents/pages/AgentListPage.tsx
features/agents/pages/AgentDetailPage.tsx
features/agents/components/AgentCard.tsx
features/agents/api.ts
~~~

角色卡片显示：

- Agent 名称作为卡片标题。
- 简短职责描述。
- 性格描述，使用次级文本。
- expertise 使用紧凑标签。
- 已配置工具使用图标或最多三项摘要，其余显示数量。
- “开始对话”是明确命令按钮，跳转 `/new?agentId=...`。

卡片采用响应式网格，但内容区不要再包一层大卡片。桌面建议 2 到 3 列，移动端单列。

### 1v1 对话页

新增：

~~~text
features/chat/pages/ChatPage.tsx
features/chat/components/ChatHeader.tsx
features/chat/components/MessageList.tsx
features/chat/components/UserMessage.tsx
features/chat/components/AgentMessage.tsx
features/chat/components/ToolEvent.tsx
features/chat/components/Composer.tsx
features/chat/hooks/useChatRun.ts
~~~

页面结构：

- `ChatHeader` 显示 Agent 名称、状态和返回角色详情入口。
- 用户消息靠右但不使用夸张气泡；Agent 消息靠左并保留较宽文本区域。
- Agent Markdown 支持标题、列表、引用、表格、行内代码和代码块。
- `ToolEvent` 使用可折叠行，显示工具图标、名称、状态、耗时和结果摘要。
- `Composer` 使用可自动增高的 textarea、发送图标按钮和停止按钮。
- Enter 发送，Shift+Enter 换行；IME 中文输入组合期间不得误发送。
- Run 进行中禁用重复发送，停止按钮调用 cancel API。
- 流式 delta 只更新当前临时消息；收到 completed 后再以服务端持久化 ID 为准刷新查询。

滚动规则：

- 用户位于消息底部时自动跟随新 token。
- 用户主动向上查看历史后停止抢占滚动，并显示“回到底部”按钮。
- 切换会话时恢复到末尾，不保留另一个会话的滚动位置。

### 权限确认

新增：

~~~text
features/permissions/components/PermissionDialog.tsx
features/permissions/components/ScopeSelector.tsx
features/permissions/types.ts
~~~

弹窗展示：

- 工具名称。
- 操作类型，例如读取文件、修改文件或执行命令。
- 资源路径；路径使用等宽字体且允许换行，不能撑破弹窗。
- `ONCE`、`SESSION`、`AGENT` 范围选择。
- 明确的拒绝和允许按钮。

默认选中 `ONCE`。允许按钮不能用模糊的“确定”；使用“允许一次”等与当前 scope 对应的文本。危险操作使用警告色，但不把普通读取请求渲染成红色危险操作。

### 设置页

新增：

~~~text
features/settings/pages/SettingsLayout.tsx
features/settings/pages/AppearanceSettingsPage.tsx
features/settings/pages/LLMSettingsPage.tsx
features/settings/pages/ToolSettingsPage.tsx
features/settings/components/SettingsNav.tsx
features/settings/theme/ThemeProvider.tsx
~~~

设置内容页使用左侧局部导航或顶部 tabs：

- 外观：系统、浅色、深色三段式选择器。
- LLM：紧凑表格，显示名称、服务商、模型、地址和凭据状态。
- 工具：列表显示名称、说明、输入参数和权限动作。

LLM 和工具列表首期不显示编辑按钮。空状态要明确表达“尚未配置”，但不放置不可用的创建按钮。

### 前端数据层

新增 `api/types.ts`，定义与 OpenAPI 一致的 DTO。不要直接复用组件 props 作为 API 类型。

新增 `api/client.ts`：

~~~text
apiClient.get<T>(path)
apiClient.post<TRequest, TResponse>(path, body)
ApiError
~~~

新增 `api/stream.ts`：

~~~text
streamPost(path, body, signal, onEvent)
parseSseStream(reader)
~~~

解析器必须正确处理：

- 一个事件被拆成多个网络 chunk。
- 一个 chunk 包含多个事件。
- UTF-8 中文字符跨 chunk。
- 注释心跳行。
- 服务端结构化错误事件。
- AbortController 主动取消。

## 分阶段实施计划

### 阶段一：工程骨架和契约

#### 任务：建立 Server 工程与应用生命周期

修改/新增：

- `client/web/server/pyproject.toml`
- `client/web/server/app/main.py`
- `client/web/server/app/config.py`
- `client/web/server/app/dependencies.py`
- `client/web/server/tests/conftest.py`

原因：先证明 Web 层能初始化现有数据库并通过依赖注入获得业务服务，避免后续路由各自创建连接。

验收：

- `GET /api/health` 返回版本和数据库状态。
- 服务默认只监听回环地址。
- 测试使用临时 workspace，不读取开发者真实数据库。
- 应用关闭后数据库连接被释放。

#### 任务：定义 API DTO 和统一错误格式

修改/新增：

- `client/web/server/app/schemas/*.py`
- `client/web/server/app/errors.py`
- `client/web/front/src/api/types.ts`

原因：Server 和 Front 可以在契约确定后并行实现，且内部字段不会意外暴露到浏览器。

验收：

- DTO 使用 camelCase JSON。
- 所有错误符合统一结构。
- LLM 响应中不存在 API Key。
- OpenAPI schema 可生成且无重复模型名。

#### 任务：建立 Front 工程和设计令牌

修改/新增：

- `client/web/front/package.json`
- `client/web/front/vite.config.ts`
- `client/web/front/src/main.tsx`
- `client/web/front/src/app/providers.tsx`
- `client/web/front/src/styles/tokens.css`
- `client/web/front/src/styles/global.css`

原因：先固定主题变量、间距、字体、边框和基础交互，后续页面不各自发明样式。

验收：

- Vite 可启动和构建。
- 浅色、深色和系统主题可切换。
- 页面不存在水平滚动条。
- 键盘焦点清晰可见。

### 检查点：工程基础

- Server pytest 全部通过。
- Front lint、typecheck、unit test 和 build 全部通过。
- OpenAPI DTO 与 TypeScript 类型逐字段核对。
- 人工确认基础色彩、字号和侧栏密度后再进入业务页面。

### 阶段二：角色发现竖切

#### 任务：实现 Agent 查询 API

修改/新增：

- `client/web/server/app/api/agents.py`
- `client/web/server/app/schemas/agent.py`
- `client/web/server/tests/test_agents_api.py`
- `code/agent/storage/repositories/agent_profile.py`

验收：

- 只列出启用 Agent。
- 支持分页和 expertise 筛选。
- 不存在的 Agent 返回稳定 404。
- API 不返回 Repository 或 SQLite 字段细节。

#### 任务：实现 AppShell 和角色页面

修改/新增：

- `layouts/AppShell.tsx`
- `layouts/Sidebar.tsx`
- `features/agents/*`
- `app/router.tsx`

验收：

- 点击“角色”进入角色列表。
- 加载、空、失败和正常状态完整。
- “开始对话”能把 agentId 带到新会话页。
- 桌面和移动端布局都不重叠、不溢出。

### 阶段三：固定 1v1 会话竖切

#### 任务：补充会话只读查询仓储

修改/新增：

- `code/agent/storage/types.py`
- `code/agent/storage/repositories/session_query.py`
- `tests/storage/test_session_query_repository.py`

验收：

- 一次查询返回会话、唯一 Agent 和最后消息摘要。
- 只返回 DIRECT 会话。
- 分页顺序稳定。
- 不产生每会话额外查询。

#### 任务：实现会话创建和历史 API

修改/新增：

- `client/web/server/app/api/sessions.py`
- `client/web/server/app/schemas/session.py`
- `client/web/server/tests/test_sessions_api.py`

验收：

- 创建接口只允许 `DIRECT`。
- Agent 不存在或禁用时不产生空 Session。
- 历史列表包含 Agent 名称和消息摘要。
- 会话详情和消息按 sequenceNo 升序返回。

#### 任务：实现新对话和历史侧栏

修改/新增：

- `features/chat/pages/NewChatPage.tsx`
- `features/agents/components/AgentPicker.tsx`
- `features/sessions/components/SessionHistory.tsx`
- `features/sessions/api.ts`

验收：

- 新对话页可以选择一个 Agent。
- 未输入消息时不创建空 Session。
- 首次发送后创建会话并更新 URL。
- 新会话立即进入历史列表并高亮。

### 检查点：1v1 数据闭环

- 能从真实 SQLite 角色配置创建 1v1 Session。
- 刷新页面后会话和历史消息仍可恢复。
- 删除或禁用状态不会被 UI 静默忽略。
- 原 Agent 核心测试与 Web API 测试全部通过。

### 阶段四：流式对话和权限闭环

#### 任务：实现 RunRegistry 和 ChatService

修改/新增：

- `client/web/server/app/services/run_registry.py`
- `client/web/server/app/services/chat_service.py`
- `client/web/server/tests/test_runs_api.py`

验收：

- 一个 Session 不可同时启动两个 Run。
- Runtime 完成后注册项被清理。
- `WAITING_PERMISSION` 时注册项保留。
- 无效 runId 和 callId 不会执行工具。

#### 任务：实现 SSE Run API

修改/新增：

- `client/web/server/app/api/runs.py`
- `client/web/server/app/schemas/run.py`
- `client/web/server/tests/test_runs_api.py`

验收：

- 文本 delta 按顺序输出。
- 完成、错误、取消和权限请求都有终止或暂停事件。
- 客户端断开时取消继续写流，但不损坏已持久化 ContextItem。
- API 不泄露异常堆栈、命令内部对象或凭据。

#### 任务：实现对话页面和 SSE 客户端

修改/新增：

- `api/stream.ts`
- `features/chat/pages/ChatPage.tsx`
- `features/chat/hooks/useChatRun.ts`
- `features/chat/components/*`

验收：

- 用户消息、流式 Agent 消息和工具事件按顺序显示。
- 中文流分片不会乱码或丢字。
- 停止按钮可取消当前 Run。
- 刷新后从持久化 ContextItem 恢复消息。

#### 任务：实现权限确认 UI 和恢复 API

修改/新增：

- `features/permissions/*`
- `client/web/server/app/api/runs.py`
- Server 与 Front 权限测试。

验收：

- ASK 时停止继续调用 LLM 并显示弹窗。
- 允许/拒绝携带正确 callId 和 scope。
- 确认后从原 Runtime 恢复，而不是新建 Agent。
- 弹窗关闭不能被误解为允许；必须显式拒绝或继续等待。

### 阶段五：设置页

#### 任务：实现 LLM 与工具只读 API

修改/新增：

- `client/web/server/app/api/settings.py`
- `client/web/server/app/schemas/settings.py`
- `client/web/server/tests/test_settings_api.py`

验收：

- LLM 列表不返回 API Key。
- 工具列表只返回可展示元数据。
- 无效工具模块不会导致整个列表失败，具体处理策略需在实施前明确测试。

#### 任务：实现主题、LLM 和工具页面

修改/新增：

- `features/settings/*`
- `features/settings/theme/ThemeProvider.tsx`

验收：

- 主题设置刷新后保留。
- 系统主题可响应操作系统变化。
- LLM 和工具列表适合快速扫描。
- 窄屏表格转换为列表，不出现横向内容遮挡。

### 阶段六：集成、视觉和可运行入口

#### 任务：统一开发命令和静态构建托管

修改/新增：

- `client/web/README.md`
- 根目录开发脚本或 `Makefile`
- `client/web/server/app/main.py`

验收：

- 一条命令启动 Server，另一条命令启动 Front 开发服务器。
- 生产构建后 FastAPI 可以同源提供 `front/dist`。
- workspace 参数使用明确绝对路径。
- 服务启动日志不打印凭据。

#### 任务：Playwright 端到端与视觉验证

修改/新增：

- `client/web/front/e2e/direct-chat.spec.ts`
- `client/web/front/e2e/navigation.spec.ts`
- `client/web/front/e2e/responsive.spec.ts`

检查 viewport：

- `1440 × 900` 桌面。
- `1024 × 768` 小屏桌面。
- `390 × 844` 手机。

验收：

- 角色选择、创建会话、发送消息、权限确认、刷新恢复完整可用。
- 明暗主题截图无不可读文本。
- 侧栏、消息、输入区和弹窗不重叠。
- 长 Agent 名称、长路径、长代码和错误文本不会撑破容器。
- 页面无严重 console error、失败网络请求和 React warning。

## 测试策略

### Agent 核心

继续运行现有测试：

~~~bash
python -m pytest -q
python -m compileall -q code
~~~

### Server

- Repository 和 Service 使用临时 SQLite workspace。
- API 使用 HTTPX ASGI client，不启动真实端口。
- LLM 使用可控 FakeLLM，禁止测试调用外部模型服务。
- SSE 测试覆盖事件顺序、权限暂停、恢复和取消。
- 安全测试检查响应中不存在 API Key 和 traceback。

### Front

- 单元测试覆盖 SSE 分片解析器、主题解析和日期分组。
- 组件测试覆盖角色卡片、会话历史、Composer 和 PermissionDialog。
- MSW 模拟 API 成功、空、失败和慢响应。
- Playwright 使用测试 Server 或稳定 fake adapter 完成端到端验证。

## 安全边界

Web Server 能触发文件工具和 Bash，风险高于普通本地页面，因此首期必须遵守：

- 默认绑定 `127.0.0.1`，不能默认监听 `0.0.0.0`。
- 不配置通配 CORS；开发环境使用固定 Vite origin 或 proxy。
- 不从 URL 接受任意 workspace 路径。
- 不向 Front 返回 API Key、环境变量值、Python 路径或堆栈。
- 工具仍必须经过现有 PermissionManager，API 不提供绕过权限的执行接口。
- 权限确认只提交 callId、decision 和 scope，服务端从 pending Runtime 读取真实资源。
- Markdown 禁止原始 HTML，链接增加安全属性，避免模型输出注入可执行 DOM。
- 服务端日志记录 requestId、sessionId 和 runId，但不记录完整凭据和敏感工具输出。
- 首期无身份认证，因此文档必须明确它只适用于本机开发环境。

## 并行开发建议

契约阶段完成后可以拆为三条并行支线：

~~~text
支线 A：Agent / Session 查询 API
支线 B：AppShell / 角色 / 设置静态页面
支线 C：RunRegistry / SSE 事件映射测试
~~~

以下工作必须串行：

- 先确定 SSE 事件 DTO，再分别实现 Server 和 Front。
- 先完成 Session 查询仓储，再实现历史会话 API。
- 先完成 RunRegistry，再实现权限恢复接口。
- 对话页完成后再写完整 Playwright 流程。

每个阶段完成后只提交该阶段相关文件，并运行对应局部测试；检查点再运行全部 Agent、Server 和 Front 测试。

## 风险与处理

| 风险 | 影响 | 处理方式 |
|---|---|---|
| Runtime 权限状态只在内存中 | 刷新或重启后无法恢复待确认工具 | 首期明确单进程限制；后续再持久化 PendingRun |
| 同一 Session 重复发送 | 两个 Runtime 同时追加上下文，顺序混乱 | RunRegistry 对 session_id 加互斥约束 |
| 会话列表出现 N+1 查询 | 历史较多时响应变慢 | 使用专用 SessionQueryRepository JOIN 查询 |
| SSE 网络分片处理错误 | 中文乱码、事件丢失 | 独立解析器并覆盖跨 chunk 测试 |
| LLM 或工具异常暴露内部信息 | 泄露路径、堆栈或凭据 | 统一错误映射和响应字段白名单 |
| Markdown 内容包含危险 HTML | 浏览器脚本注入 | 禁用 raw HTML，不使用 `dangerouslySetInnerHTML` |
| UI 先于契约随意开发 | Server/Front 字段反复变更 | 第一阶段冻结 Pydantic DTO 和 TS 类型 |
| 新增前端依赖过多 | 学习和维护成本增加 | 状态库限制为 TanStack Query，局部状态使用 React |

## 完成标准

完成本计划后，用户应能：

1. 在角色页面查看数据库中已启用的 Agent。
2. 从新对话页选择一个 Agent 并发送第一条消息。
3. 自动创建固定 Agent 的 DIRECT Session。
4. 在对话页看到流式 Agent 回复和工具执行记录。
5. 在权限请求出现时选择拒绝或按 ONCE、SESSION、AGENT 范围允许。
6. 从左侧历史列表切换会话，并在刷新后恢复已持久化消息。
7. 在设置中切换主题并查看 LLM、工具列表。
8. 在桌面和移动 viewport 下完成上述核心流程，不出现布局重叠或内容溢出。

本阶段完成后，再评估 GROUP 群聊 UI。群聊应建立在已经稳定的 Session、流事件和权限交互契约上，而不是提前把多 Agent 调度逻辑塞入首个 Web 版本。
