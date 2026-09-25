# 子 Agent 开发迭代计划（未施工）

> 状态：未施工。该计划当前仅作为后续设计参考，暂不进入实现阶段。

> 当前接口说明：本计划最初基于 `Runtime.run(context)` 编写；Agent/Runtime 收口完成后，正式接口已经变为 `Agent.run()` 和 `Agent.resolve_permission(response)`，Runtime 的 Context 在构造时绑定。子 Agent 计划仍未施工，后续施工时以《Agent 与 Runtime 职责收口施工计划》后的实际接口为准。

## 1. 文档目的

本文档定义第一版子 Agent 的产品边界、最小架构、模块职责、开发阶段和验收标准。

第一版只支持 `DIRECT` / 一对一 Session。子 Agent 由主 Agent 创建和调用，是由正式 Session 管理的临时执行实例：不进入正式 Session 存储、不出现在历史会话列表中，Context 只保存在内存中，并在生命周期结束后销毁。

本计划基于当前代码的真实职责划分：

- `Agent` 保存稳定身份、Profile、LLM 配置和 Tool 定义，不保存 Session 状态。
- `Runtime` 负责 Agent Loop，并在 `run(context)` 时接收调用方提供的 `Context`。
- `Context` 本身是内存对象，已经具备消息追加、工具协议项管理、上下文精简、压缩、`export()` 和 `restore()`。
- `ContextService` 只用于正式 Session 的数据库时间线和 Context 快照持久化。
- `SessionService` / `SessionExecution` 负责为一次正式 Session 组装 Context、Runtime、权限和进程环境。

因此，子 Agent 不需要新的 Agent 类型，不需要修改 Runtime，也不需要新增临时存储服务。

## 2. 最终产品形态

用户在一个一对一会话中与主 Agent 对话。主 Agent 根据任务需要调用 `subagent` Tool，创建一个临时子 Agent，或复用当前正式 Session 中仍然存活且空闲的子 Agent。

每个子 Agent：

- 使用与主 Agent 相同的角色、LLM 配置和四个基础 Tool。
- 拥有独立的 `Context` 和独立的 `Runtime` 实例。
- 继承父 Session 的工作目录、权限模式和 Session 权限规则。
- 在后台执行一个任务；同一时刻不能并行处理两个任务。
- 完成后进入空闲状态，在 TTL 到期前可以复用。
- Context 在复用期间保留，TTL 到期或父 Session 关闭时销毁。
- 不写入 `sessions`、`session_agents`、`context_items` 或其他正式业务表。

用户在主会话右上角看到当前存活子 Agent 的名称、任务摘要和状态。点击后可以查看该子 Agent 的临时 Context，但不能直接发送消息。

```text
正式 DIRECT Session
├── 主 Agent Runtime
├── 正式 Context（通过 ContextService 持久化）
├── Session PermissionManager
└── ChildSessionManager（由 SessionService 按正式 Session 保留）
    ├── ChildSessionExecution A
    │   ├── Context（现有类，纯内存）
    │   ├── Runtime（现有类，独立实例）
    │   ├── SessionProcessManager（独立实例）
    │   └── 状态、任务、结果、TTL
    └── ChildSessionExecution B
        ├── Context（现有类，纯内存）
        ├── Runtime（现有类，独立实例）
        ├── SessionProcessManager（独立实例）
        └── 状态、任务、结果、TTL
```

## 3. 核心设计结论

### 3.1 子 Agent 的区别在 Session，不在 Agent

不新增 `ChildAgent`、`SubAgent` 或特殊 Agent Profile。

当前 `Agent` 是稳定角色配置，不携带 Context、权限等待、工具队列或子任务状态。子 Agent 继续使用同一个逻辑 Agent 的配置；父子差异由临时 `ChildSessionExecution` 表达。

第一版不能从已有 Agent Profile 列表中选择另一个角色。创建子 Agent 时直接继承当前主 Agent 的：

- `agent_id`
- Profile 和系统指令
- LLM 配置
- 基础 Tool 定义

### 3.2 Context 直接使用现有类

子 Session 直接创建：

```python
Context(child_llm, session_id=child_session_id)
```

不新增 `TransientContextService`，不抽象 Context 存储 Protocol，也不修改 `ContextService`。

原因：

- `Context` 已经是纯内存对象。
- 子 Context 不需要恢复数据库时间线。
- 子 Context 不需要保存当前快照到数据库。
- `context.export()` 已经可以支持 UI 的只读查看。
- `Context` 内部已经会根据模型使用量进行工具结果精简和上下文压缩。

子 Agent 生命周期结束时，`ChildSessionManager` 删除对 Context 的引用即可。这里不存在需要 storage Adapter 解决的变化点。

### 3.3 Runtime 类保持不变，但实例必须隔离

不修改：

- `code/agent/runtime/runtime.py`
- `code/agent/runtime/agent.py`
- `code/agent/runtime/agent_factory.py`

子 Session 复用现有 `Runtime` 类，但每个子 Session 创建独立实例。

不能让主 Agent 和子 Agent 共用一个 Runtime 实例，因为 Runtime 内部保存：

- 当前 `IDLE` / `RUNNING` / `WAITING_PERMISSION` 状态。
- 当前 pending Tool Call。
- 后续 Tool Call 队列。
- 取消状态。

共享实例会导致子 Agent 等待权限时阻塞主 Agent，或者多个任务覆盖同一个 pending 调用。

这里需要的是在 Session 层复用现有 Runtime 组装代码，不是修改 Runtime 接口，也不是新增 `SessionAgentRuntimeFactory`。

### 3.4 不新增 ParentSessionBridge

父子 Session 的以下交互全部由 `ChildSessionManager` 管理：

- 创建和复用子 Session。
- 启动后台任务。
- 保存运行状态和最终结果。
- 保存子 Runtime 产生的 pending 权限请求。
- 根据 `child_session_id + call_id` 恢复正确的 Runtime。
- 停止任务、清理进程和执行 TTL 销毁。

不新增 `ParentSessionBridge`，也不建立另一套子任务注册表。第一版只有一个父子管理入口，避免职责重复。

### 3.5 子 Session 不落库

子 Session 不创建或更新：

- `sessions`
- `session_agents`
- `context_items`
- `session_permission_rules` 中的新 Session 归属
- Agent Profile 或 LLM Profile

子 Agent 可以使用父 Session 已经存在的 Session 权限规则。子任务结果只有作为 `subagent` Tool Result 返回给主 Runtime 后，才会按现有 Runtime 行为进入主 Context。

子 Agent 的内部消息、工具调用和工具结果不会自动复制到正式 Session 时间线。

### 3.6 权限继承不修改 Runtime

子 Runtime 复用父 Session 的同一个 `PermissionManager`。

构造子 Runtime 的 `ExecutionContext` 时：

- `project_path` 使用父 Session 工作目录。
- `agent_id` 使用主 Agent ID。
- `session_id` 使用正式父 Session ID，而不是临时 child ID。
- `process_manager` 使用子 Session 自己的 `SessionProcessManager`。

`ExecutionContext.session_id` 在 Tool 权限请求中代表权限归属 Session。这样现有 `PermissionManager` 的 Session 校验、规则读取和规则写入都继续落在正式父 Session，不需要引入 `permission_session_id` 或修改 Runtime。

临时 child ID 由 `ChildSessionManager` 单独保存，用来定位子 Runtime、状态和 Context。

### 3.7 第一版使用状态查询，不增加内部事件总线

子 Runtime 在后台线程中运行，`ChildSessionManager` 直接更新线程安全状态。

- 主 Agent 通过 `subagent.status` / `subagent.wait` 获取结果。
- Web UI 通过定时查询子 Agent API 获取状态。
- 子 Agent 等待权限时，UI 查询结果包含 pending 权限请求。
- 用户确认后，API 直接调用 `ChildSessionManager.resolve_permission()`。

第一版不增加内部事件队列、父子 callback 总线或子 Agent SSE。轮询频率应保持克制：运行中/等待权限时快速轮询，全部空闲时降低频率或停止轮询。

这个方案与当前同步 Runtime generator 更匹配，也避免 callback 重入主 Runtime。

## 4. 临时对象与状态

### 4.1 ChildSessionExecution

新增一个轻量的临时执行对象，可以使用 dataclass。建议字段：

| 字段 | 说明 |
| --- | --- |
| `id` | 临时 child Session ID |
| `parent_session_id` | 正式父 Session ID |
| `agent_id` | 继承的主 Agent ID |
| `name` | 模型生成或创建参数提供的显示名称 |
| `context` | 现有 `Context` 实例 |
| `runtime` | 现有 `Runtime` 的独立实例 |
| `process_manager` | 子 Session 独立后台进程管理器 |
| `status` | 当前生命周期状态 |
| `task_id` | 当前或最近任务 ID |
| `task_prompt` | 当前或最近任务说明 |
| `result` | 最近任务结果摘要 |
| `error` | 最近失败的稳定错误信息 |
| `pending_permission` | 当前等待用户确认的权限事件 |
| `created_at` | 创建时间 |
| `last_activity_at` | 最近活动时间 |
| `idle_timer` | 空闲 TTL 定时器；运行时取消，进入 idle 时重建 |

这个对象只存在于内存中，不复用正式 `storage.types.Session`，避免临时对象被误传给 Repository。

### 4.2 状态枚举

第一版状态：

```text
CREATED
RUNNING
WAITING_PERMISSION
IDLE
FAILED
STOPPING
DESTROYED
```

状态转换：

```text
CREATED -> RUNNING
RUNNING -> WAITING_PERMISSION -> RUNNING
RUNNING -> IDLE
RUNNING -> FAILED
RUNNING -> STOPPING -> DESTROYED
IDLE -> RUNNING
FAILED -> RUNNING（显式复用并开始新任务）
IDLE -> DESTROYED（TTL 或显式停止）
FAILED -> DESTROYED（TTL 或显式停止）
任意非 DESTROYED 状态 -> DESTROYED（父 Session 关闭）
```

约束：

- 一个子 Session 同一时刻只能有一个任务。
- `RUNNING` 和 `WAITING_PERMISSION` 不能被复用。
- `WAITING_PERMISSION` 不计算空闲 TTL。
- 任务成功后进入 `IDLE`；失败后保留 `FAILED` 供 UI 查看。两者都启动 TTL Timer。
- `IDLE` 和 `FAILED` 都可以通过显式 `run` 复用，复用时清除上一次错误。
- 复用时保留已有 Context，生成新的 `task_id`。
- `DESTROYED` 是终态，不能重新激活。

### 4.3 线程安全

`ChildSessionManager` 使用一个 `RLock` 保护：

- child 字典。
- 状态转换。
- 当前任务和结果。
- pending 权限请求。
- Timer 创建和取消。

执行 LLM 和 Tool 时不能长时间持有 Manager 锁。正确流程是：锁内校验并切换状态，锁外消费 Runtime generator，收到事件后短暂加锁更新状态。

每个子任务使用独立后台线程。第一版可以使用受限 `ThreadPoolExecutor`，worker 数量不得超过每个正式 Session 允许的最大存活子 Agent 数。

## 5. 模块和文件改动

### 5.1 新增 `session/child_session.py`

路径：

```text
code/agent/session/child_session.py
```

包含：

- `ChildSessionStatus`
- `ChildSessionExecution`
- `ChildSessionSummary`
- 必要的稳定错误类型

不包含：

- SQL 或 Repository。
- Agent Profile 加载。
- Runtime 实现。
- Web schema。
- Tool 注册逻辑。

### 5.2 新增 `session/child_session_manager.py`

路径：

```text
code/agent/session/child_session_manager.py
```

职责：

- 创建和保存临时 `ChildSessionExecution`。
- 接收 SessionService 注入的 Runtime/Context 创建回调。
- 在后台线程中消费现有 Runtime generator。
- 保存子 Agent 的状态、结果和错误。
- 保存和恢复 pending 权限请求。
- 实现 list/status/wait/inspect/stop。
- 管理 TTL Timer。
- 销毁子 ProcessManager、Runtime 和 Context 引用。

不负责：

- 创建正式 Session。
- 访问 SessionRepository、ContextItemRepository。
- 修改主 Context。
- 重新实现 Agent Loop。
- 构造 Agent Profile。

建议最小接口：

```python
class ChildSessionManager:
    def spawn(self, task: str, *, name: str | None = None) -> ChildSessionSummary: ...
    def run(self, child_session_id: str, task: str) -> ChildSessionSummary: ...
    def list(self) -> list[ChildSessionSummary]: ...
    def status(self, child_session_id: str) -> ChildSessionSummary: ...
    def wait(self, child_session_id: str, timeout: float | None = None) -> ChildSessionSummary: ...
    def inspect(self, child_session_id: str) -> list[dict]: ...
    def resolve_permission(self, child_session_id: str, response: PermissionResponse) -> None: ...
    def stop(self, child_session_id: str) -> None: ...
    def close(self) -> None: ...
```

`wait()` 必须有本地最大 timeout，不能让一个 Tool 调用无限阻塞。

### 5.3 修改 `session/session_service.py`

这是核心组装位置，但改动限制在 Session 层。

需要修改：

1. 为每个打开的正式 DIRECT Session 获取或创建一个 `ChildSessionManager`。
2. Manager 按正式 `session_id` 保存在 `SessionService` 中，使它不会随着一次 Web Run 结束而丢失。
3. 使用现有 Agent 配置、父 PermissionManager 和父 workspace 创建子 Runtime。
4. 子 Runtime 只注册 Agent 原有基础 Tool，不注册 `subagent`。
5. 主 Runtime 在 DIRECT 模式下额外注册绑定当前 Manager 的 `subagent` Tool。
6. `GROUP` Session 不注册 `subagent`。
7. 增加 `close_session(session_id)` 和 `close()`，用于关闭单个或全部 Manager。
8. 服务关闭或正式 Session 关闭时调用 Manager.close()。

现有 `_create_runtime()` 可以做最小参数整理，以便父 Runtime 和子 Runtime 共用同一段组装代码；不新增 Runtime Factory 类。

建议将当前依赖 `SessionAgent` 的私有参数收缩为运行真正需要的值：

```python
def _create_runtime(
    agent: Agent,
    *,
    permission: PermissionManager,
    permission_mode: str,
    project_path: str | None,
    permission_session_id: str,
    process_manager: SessionProcessManager,
    extra_tools: tuple[Tool, ...] = (),
) -> Runtime:
    ...
```

这是 `SessionService` 内部组装方法，不改变 Runtime 接口。`permission_session_id` 只用于创建 `ExecutionContext.session_id`，不需要加入 Runtime 或权限领域类型。

### 5.4 新增 `tools/orchestration/subagent.py`

路径：

```text
code/agent/tools/orchestration/subagent.py
```

不放到基础 Tool 根目录。建议通过创建函数绑定当前 Manager：

```python
def create_subagent_tool(manager: ChildSessionManager) -> Tool:
    ...
```

这样 Tool 不需要从 `ExecutionContext` 查找 Manager，也不需要全局 Session 单例。

第一版 action：

| action | 必要参数 | 行为 |
| --- | --- | --- |
| `spawn` | `task` | 创建子 Session 并立即开始任务 |
| `run` | `child_session_id`, `task` | 复用一个空闲子 Session |
| `list` | 无 | 列出当前父 Session 的存活子 Agent |
| `status` | `child_session_id` | 返回状态、任务和结果摘要 |
| `wait` | `child_session_id`, 可选 `timeout` | 有界等待，返回当前或终态结果 |
| `inspect` | `child_session_id` | 返回截断后的只读 Context |
| `stop` | `child_session_id` | 停止并销毁子 Session |

Tool 约束：

- 不接受 `agent_id`，只能继承当前主 Agent。
- 不接受 `workspace_path` 或 `permission_mode`。
- 不接受父 `session_id`，绑定关系由 Tool 闭包确定。
- 所有字符串、Context 和结果都有本地长度上限。
- `wait` 有最大等待时间。
- `inspect` 不返回 LLM API Key、Runtime 对象或 PermissionManager 内容。

### 5.5 修改 Tool 通用准备逻辑

当前 `Tools.prepare_call()` 在解析具体 Tool 前统一要求存在 workspace。这样空工作目录 Session 无法调用不需要文件系统的 `subagent` Tool。

需要在现有 Tool 元数据中增加一个简单标记，例如：

```python
requires_workspace: bool = True
```

- `read`、`write`、`edit`、`bash` 保持默认 `True`。
- `subagent` 设置为 `False`。
- `Tools.prepare_call()` 只在目标 Tool 要求 workspace 时返回 `PROJECT_NOT_SELECTED`。

这是支持空项目对话调用子 Agent 所需的最小改动，不属于 Runtime 改造。

涉及：

- `code/agent/tools/types.py`
- `code/agent/tools/tools.py`
- 对应 Tool 准备测试

### 5.6 权限处理

不修改 Runtime 权限暂停/恢复协议，也不新增 `execution_id`。

子 Runtime 产生 `PermissionRequiredEvent` 后，Manager 保存：

```text
child_session_id
task_id
call_id
PermissionRequiredEvent
Runtime 引用
Context 引用
```

用户确认时必须提交：

```text
parent_session_id
child_session_id
call_id
decision
scope
```

Manager 校验 child 归属于 parent，且 `call_id` 与当前 pending 调用一致，然后调用：

```python
child.runtime.resolve_permission(child.context, response)
```

因为 PermissionRequest 的 `session_id` 已经是正式父 Session ID，所以：

- `once` 只影响当前调用。
- `session` 规则保存到父 Session。
- `deny` / `don't ask` 沿用现有父 Session 规则语义。
- plan/build/yolo 和硬安全规则继续由现有 PermissionManager 判断。

`subagent` Tool 自身只做 Session 内部编排，不直接访问文件或执行命令。建议新增 `PermissionAction.SUBAGENT_MANAGE`，并在现有模式策略中默认允许；真正的文件和 Shell 权限仍由子 Runtime 调用基础 Tool 时检查。

### 5.7 Web 服务端

新增：

```text
client/web/server/app/schemas/subagent.py
client/web/server/app/api/subagents.py
```

建议接口：

```text
GET  /api/sessions/{session_id}/subagents
GET  /api/sessions/{session_id}/subagents/{child_session_id}
GET  /api/sessions/{session_id}/subagents/{child_session_id}/context
POST /api/sessions/{session_id}/subagents/{child_session_id}/permission
POST /api/sessions/{session_id}/subagents/{child_session_id}/stop
```

不提供：

```text
POST /api/sessions/{session_id}/subagents/{child_session_id}/messages
```

所有接口必须先确认：

- 正式 Session 存在且为 DIRECT。
- child ID 属于该父 Session。
- child 尚未销毁。
- 权限响应的 call ID 与 pending 调用一致。

Web API 直接通过 `SessionService` 获取对应 `ChildSessionManager`，不访问数据库查询 child。

### 5.8 Web 前端

新增建议目录：

```text
client/web/front/src/features/subagents/
├── api.ts
├── components/SubagentPanel.tsx
├── components/SubagentContextView.tsx
└── components/SubagentStatus.tsx
```

修改：

- `client/web/front/src/api/types.ts`
- `client/web/front/src/features/chat/pages/ChatPage.tsx`
- 主会话权限弹窗的来源显示和提交逻辑
- 对应 CSS 和测试

轮询策略：

- 存在 `RUNNING` 或 `WAITING_PERMISSION` 子 Agent 时，每 1-2 秒查询。
- 全部为 `IDLE` 时降低到 5-10 秒，或在面板关闭时停止轮询。
- 页面不可见时暂停高频轮询。
- 父 Session 切换后立即取消旧 Session 的查询。

UI 要求：

- 宽屏时在主会话右上区域显示悬浮面板。
- 宽度不足时隐藏，不遮挡消息和输入框。
- 展示名称、任务摘要、运行状态和等待权限状态。
- 点击后只读查看 Context。
- 不显示输入框或发送按钮。
- child 销毁后从列表移除。

## 6. 开发阶段

### 阶段 0：冻结现有行为

**目的**：确保子 Agent 改造不破坏当前正式 Session、Runtime、Context 和权限行为。

**工作内容**：

- 运行并记录当前 Python、Web 服务端和前端测试基线。
- 补充 `Runtime.run(context)` 使用不同 Context 的隔离测试。
- 补充 SessionService 创建 Runtime 的现有契约测试。
- 补充 Context 压缩后 `export()` 可直接用于查看的测试。
- 明确数据库行数基线，后续验证 child 不落库。

**文件**：

- `tests/runtime/test_runtime_context_contract.py`
- `tests/session/test_session_service.py`
- `tests/context/test_context_governance.py`

**验收**：

- 所有现有测试通过。
- 没有生产代码改动。
- 后续测试可以证明子 Agent 没有写正式数据库。

### 阶段 1：实现临时 ChildSessionManager

**目的**：完成纯内存子 Session 生命周期，不接 Web UI。

**工作内容**：

- 新增 `ChildSessionExecution` 和状态枚举。
- 新增 `ChildSessionManager`。
- 实现创建、后台运行、状态查询、有界等待、Context 查看、停止和销毁。
- 使用现有 `Context`，不调用 `ContextService`。
- 实现状态锁和每 child TTL Timer。
- 为每个 child 创建独立 `SessionProcessManager`。
- 任务结束进入 IDLE；空闲复用保留 Context。
- 父 Manager 关闭时停止所有 Runtime 和后台进程。

**文件**：

- 新增 `code/agent/session/child_session.py`
- 新增 `code/agent/session/child_session_manager.py`
- 新增 `tests/session/test_child_session_manager.py`

**验收**：

- 可以在不启动真实 LLM 的测试中完成状态转换。
- 两个 child 的 Context、Runtime 状态和进程管理互不影响。
- RUNNING/WAITING_PERMISSION child 不会被复用或 TTL 销毁。
- IDLE child 到期后自动销毁。
- 全过程不新增或修改任何正式 Session/ContextItem 数据。

**依赖**：阶段 0。

### 阶段 2：Session 组装和 `subagent` Tool

**目的**：让主 Agent 使用现有 Runtime 创建和调用子 Agent。

**工作内容**：

- `SessionService` 按正式 Session ID 保留 Manager。
- 调整 `SessionService._create_runtime()` 的私有参数，供父/子复用。
- 子 Runtime 使用现有 Runtime 类、独立 Context 和独立 ProcessManager。
- 子 Runtime 使用父 Session PermissionManager 和父 Session ID。
- DIRECT 主 Runtime 动态注册绑定 Manager 的 `subagent` Tool。
- GROUP Runtime 不注册该 Tool。
- 子 Runtime 只注册基础 Tool，不能创建孙 Agent。
- 实现 subagent action 参数校验和稳定 ToolResult。
- 让不需要 workspace 的 Tool 在空项目 Session 中可运行。

**文件**：

- 修改 `code/agent/session/session_service.py`
- 新增 `code/agent/tools/orchestration/__init__.py`
- 新增 `code/agent/tools/orchestration/subagent.py`
- 修改 `code/agent/tools/types.py`
- 修改 `code/agent/tools/tools.py`
- 新增 `tests/tools/test_subagent_tool.py`
- 修改 `tests/session/test_session_service.py`
- 修改 `tests/test_tool_preparation.py`

**验收**：

- 主 Agent 可以完成 spawn/list/status/wait/inspect/run/stop。
- 子 Agent 没有 `subagent` Tool。
- GROUP Session 无法创建子 Agent。
- 无 workspace 的 DIRECT Session 仍可运行 subagent 对话任务。
- 子 Agent 的内部 Context 不进入主 Session 时间线。
- SessionService 后续重新 load 同一正式 Session 时仍能取得原 Manager 和存活 child。

**依赖**：阶段 1。

### 阶段 3：权限请求透传

**目的**：让子 Agent 完整继承父 Session 权限，并由主会话 UI 确认。

**工作内容**：

- Manager 捕获子 Runtime 的 `PermissionRequiredEvent`。
- 保存 child、task、call ID 与 Runtime/Context 的对应关系。
- 实现 `resolve_permission(child_session_id, response)`。
- 检查 child 归属和 call ID，拒绝重复、过期或错配响应。
- 用户确认后在后台继续消费同一个 Runtime generator。
- 等待权限期间取消 TTL。
- 验证 `session` 规则写入父 Session，并影响同一正式 Session 后续主/子调用。
- 为 `SUBAGENT_MANAGE` 增加默认允许的模式策略。

**文件**：

- 修改 `code/agent/session/child_session_manager.py`
- 必要时修改 `code/agent/permission/types.py`
- 必要时修改 `code/agent/permission/policies.py`
- 新增 `tests/session/test_child_session_permissions.py`
- 修改 `tests/test_permission_manager.py`

**明确不改**：

- `runtime/runtime.py`
- `runtime/runtime_events.py`
- `runtime/agent.py`
- `runtime/agent_factory.py`

**验收**：

- plan/build/yolo 行为与父 Session 一致。
- 子 Agent 不能绕过 workspace 和硬安全策略。
- once 只恢复当前 child 调用。
- session 规则保存到父 Session。
- 错误 child ID 或 call ID 不会恢复任何 Runtime。
- 多个 child 同时等待权限时不会串线。

**依赖**：阶段 2。

### 阶段 4：Web API 和只读 UI

**目的**：让用户在主会话查看子 Agent、处理权限和查看临时 Context。

**工作内容**：

- 增加 child 列表、详情、Context、权限确认和停止接口。
- 增加父子归属校验。
- 前端增加子 Agent 面板和只读 Context 查看。
- 根据状态采用分级轮询。
- 复用现有 PermissionDialog 视觉和选项，但提交到 child 权限接口。
- 权限弹窗显示来源子 Agent 名称和任务摘要。
- 窄屏隐藏面板，不影响后台任务。
- 页面刷新后重新查询当前进程中仍存活的 child。

**文件**：

- 新增 `client/web/server/app/schemas/subagent.py`
- 新增 `client/web/server/app/api/subagents.py`
- 修改 `client/web/server/app/api/router.py`
- 必要时修改 `client/web/server/app/dependencies.py`
- 新增 `client/web/server/tests/test_subagents_api.py`
- 修改 `client/web/front/src/api/types.ts`
- 新增 `client/web/front/src/features/subagents/api.ts`
- 新增 `client/web/front/src/features/subagents/components/SubagentPanel.tsx`
- 新增 `client/web/front/src/features/subagents/components/SubagentContextView.tsx`
- 修改 `client/web/front/src/features/chat/pages/ChatPage.tsx`
- 修改权限弹窗及对应测试

**验收**：

- API 只能查询当前父 Session 的 child。
- UI 只能查看，不能向 child 发消息。
- 运行、等待权限、空闲、失败状态正确显示。
- 用户确认权限后对应 child 继续执行。
- 刷新不会把 child 变成正式历史会话。
- child 销毁后从面板移除。

**依赖**：阶段 3。

### 阶段 5：生命周期收口和回归验证

**目的**：清理资源、关闭边缘情况并更新架构文档。

**工作内容**：

- 服务退出时调用 `SessionService.close()`。
- 正式 Session 关闭时销毁对应 Manager。
- 覆盖 LLM 失败、Tool 失败、权限等待时停止、TTL 同时触发、重复 stop。
- 验证子后台进程在 child 销毁时停止。
- 验证 Manager 销毁后不再持有 Context、Runtime、Timer 和进程引用。
- 验证数量上限、任务长度、Context inspect 长度和 wait timeout。
- 更新数据持久化和上下文/运行时文档，说明子 Session 不持久化。
- 检查 tools 根目录仍只保留基础 Tool，subagent 位于 orchestration。

**文件**：

- 修改应用关闭入口/服务容器
- 补充 Session、Tool、API 和前端回归测试
- 更新 `docs/数据持久化方案.md`
- 必要时更新 `docs/plan/上下文与运行时架构更新迭代计划.md`

**验收**：

- Python 全量测试通过。
- Web 服务端全量测试通过。
- Web 前端测试和构建通过。
- 浏览器宽屏和窄屏交互验证通过。
- 没有子 Session 数据写入正式业务表。
- 没有后台线程、Timer 或子进程残留。

**依赖**：阶段 4。

## 7. 稳定错误码

至少提供：

```text
SUBAGENT_UNSUPPORTED_SESSION_MODE
SUBAGENT_NOT_FOUND
SUBAGENT_BUSY
SUBAGENT_DESTROYED
SUBAGENT_TASK_NOT_FOUND
SUBAGENT_PERMISSION_PENDING
SUBAGENT_PERMISSION_MISMATCH
SUBAGENT_ALREADY_STOPPED
SUBAGENT_LIMIT_REACHED
SUBAGENT_WAIT_TIMEOUT
SUBAGENT_INVALID_ARGUMENT
SUBAGENT_INTERNAL_ERROR
```

错误中不能包含堆栈、API Key、数据库路径、Runtime 对象或其他 Session 数据。

## 8. 资源限制

以下值必须通过配置或集中常量管理，不能散落在 Manager 方法中：

- 每个正式 Session 最大存活子 Agent 数。
- 子任务说明最大字符数。
- 子 Agent 名称最大字符数。
- `inspect` 最大返回字符数和最大消息数。
- `wait` 默认和最大 timeout。
- 子 Agent idle TTL。
- Manager worker 数量。
- 结果摘要最大字符数。

第一版建议采用保守默认值，并在测试中使用更短配置验证边界。所有限制都是本地限制，不依赖第三方 LLM 服务端。

## 9. 第一版不做的事情

- GROUP Session 子 Agent。
- OPEN/Stanford Town 式自由对话。
- 孙 Agent或递归 Agent树。
- 从已有 Agent Profile列表选择其他角色。
- 子 Agent独立 workspace、权限模式或权限规则。
- 子 Session数据库持久化和进程重启恢复。
- 用户直接向子 Agent发送消息。
- 自动把子 Context合并到主 Context。
- 修改 Runtime、Agent、AgentFactory 或 Context 的现有接口。
- 新增 TransientContextService、Context 存储抽象或 ParentSessionBridge。
- 为子 Agent增加独立 SSE 或内部事件总线。

## 10. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 父子 Agent 共用 Runtime 导致状态覆盖 | 高 | 每个 child 创建独立现有 Runtime 实例 |
| Manager 随一次 Web Run 结束而丢失 | 高 | SessionService 按正式 Session ID 保留 Manager |
| 子权限请求被错误地当成临时 Session权限 | 高 | ExecutionContext.session_id 使用父 Session ID |
| 权限响应恢复了错误 child | 高 | Manager 按 parent + child + call ID 三重校验 |
| 子 Context被写入正式时间线 | 高 | Manager只持有 Context，不注入 ContextService/Repository |
| 子 Agent递归创建孙 Agent | 高 | 子 Runtime不注册 subagent Tool |
| TTL 与任务完成同时修改状态 | 中 | RLock 保护状态；Timer回调再次确认状态和版本 |
| 子进程在 child 销毁后残留 | 高 | child 独立 ProcessManager；销毁时 stop_all |
| 空 workspace 无法使用 subagent | 中 | Tool增加 requires_workspace 元数据 |
| UI高频轮询造成无效请求 | 中 | 运行态快速、空闲态降频、页面隐藏暂停 |
| Context查看返回过多内容 | 中 | inspect按消息数和字符数双重截断 |

## 11. 完成检查清单

### Session 与 Runtime

- [ ] 子 Agent使用现有 Agent配置，不新增 Agent类型。
- [ ] 每个 child 有独立 Runtime实例。
- [ ] Runtime、Agent、AgentFactory代码没有为子 Agent增加特殊分支。
- [ ] 子 Runtime没有 subagent Tool。
- [ ] 同一个 child不能同时执行两个任务。
- [ ] SessionService重新加载正式 Session后仍能找到存活 child。

### Context 与持久化

- [ ] 子 Agent直接使用现有 Context。
- [ ] 没有 TransientContextService。
- [ ] 没有修改 ContextService来适配临时 Context。
- [ ] child 创建、运行、完成和销毁均不写正式业务表。
- [ ] Context治理后的数据在 child生命周期内继续使用。
- [ ] child销毁后 Context引用被释放。

### 权限

- [ ] 子 Runtime复用父 PermissionManager。
- [ ] PermissionRequest.session_id是正式父 Session ID。
- [ ] plan/build/yolo与父 Session一致。
- [ ] once/session/deny/don't ask语义保持不变。
- [ ] 多 child权限请求不会串线。
- [ ] 等待权限时不会触发 TTL。

### Tool 与生命周期

- [ ] spawn/run/list/status/wait/inspect/stop全部可用。
- [ ] 空 workspace可以调用 subagent，但子基础文件 Tool仍返回 PROJECT_NOT_SELECTED。
- [ ] idle child可复用且保留 Context。
- [ ] TTL到期、显式 stop、父 Session关闭均可销毁 child。
- [ ] child后台进程随 child销毁而停止。

### Web UI

- [ ] 宽屏显示右上角子 Agent面板。
- [ ] 窄屏不遮挡消息和输入框。
- [ ] Context页面只读且没有输入框。
- [ ] 等待权限可在主会话确认。
- [ ] 页面刷新后显示当前进程仍存活的 child。
- [ ] child不出现在正式历史会话列表。

## 12. 建议提交顺序

```text
test: freeze child session contracts
feat: add in-memory child session lifecycle
feat: add subagent orchestration tool
feat: forward child permissions through parent session
feat: expose child session APIs
feat: add read-only child agent panel
test: close child session lifecycle gaps
docs: document transient child sessions
```

每个阶段提交前必须：

- 运行本阶段相关测试。
- 检查 `git diff` 和暂存内容。
- 不提交 `.harness/state.db`。
- 不混入无关格式化或目录重构。
- 在本计划中记录实现偏差；如果实际需要修改 Runtime、Context 或新增存储层，必须先解释现有接口为何无法满足，再修改计划。
