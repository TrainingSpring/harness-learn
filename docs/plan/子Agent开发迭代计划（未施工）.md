# 子 Agent 开发迭代计划（未施工）

> 状态：未施工。
>
> 本计划已根据《Agent 与 Runtime 职责收口施工计划》的实际结果更新，暂不进入实现阶段。
> 本文只描述子 Agent 的后续设计，不代表代码已经支持子 Agent。

## 1. 计划目标

第一版子 Agent 只服务于 `DIRECT` 一对一正式 Session。

主 Agent 通过 `subagent` Tool 创建临时子 Agent，交给它执行独立任务。子 Agent 使用现有的 `Agent`、`Context` 和 `Runtime`，但拥有独立的临时 Session 状态：

- 不写入正式会话、消息时间线或 Agent 配置表。
- 不出现在正式会话历史列表中。
- Context 只存在于内存中，随子 Session 销毁。
- 拥有独立 Runtime、工具执行状态和后台进程管理器。
- 继承父 Session 的工作目录、权限模式和权限规则。
- 用户只能在主会话中查看状态、查看只读 Context 和处理权限请求，不能直接向子 Agent 发消息。

核心组装关系：

```text
SessionExecution
    -> 创建临时子 Session 的 Context
    -> 使用 AgentFactory 创建完整 Agent
    -> Agent 自己创建 Runtime
    -> ChildSessionManager 管理生命周期、任务和权限路由
```

## 2. 与当前架构的衔接

当前已经确定的职责：

- `Agent` 是完整运行对象，不再是 `AgentProfile` 的运行时包装数据。
- `Agent` 持有身份字段、LLM、Tools、ExecutionContext、PermissionManager、Context 和 Runtime。
- `AgentFactory.load()` 从 storage 配置加载数据，创建当前 Session 专属的完整 Agent。
- `Runtime` 构造时绑定一个 `Context`。
- `Agent.run()` 委托给内部 Runtime 的 `run()`。
- `Agent.resolve_permission(response)` 委托给内部 Runtime 的 `resolve_permission(response)`。
- `SessionService` / `SessionExecution` 创建、恢复和持久化正式 Session 的 Context。
- GROUP 成员 Agent 共享正式 Context，但拥有独立 Runtime。

子 Agent 施工时必须遵守以下边界：

- 不把 `Context` 再传入 `Runtime.run()` 或 `Runtime.resolve_permission()`。
- 不在 Session 中直接创建 Runtime、LLM 或 Tools。
- 不新增 `SessionAgentRuntimeFactory` 或其他 Runtime 工厂。
- 不新增 `TransientContextService`、临时 Context Repository 或数据库适配层。
- 不新增 `ChildAgent`、`SubAgent` 等 Agent 子类。
- 不让主 Agent 与子 Agent 共用 Runtime。
- 不让子 Agent 通过 Agent Profile 列表选择另一个持久化角色。

## 3. 最终产品形态

```text
正式 SessionExecution
├── 正式 Context                # 持久化
├── 主 Agent                    # 持有正式 Context 和 Runtime
└── ChildSessionManager
    ├── ChildSession A
    │   ├── 临时 Context         # 独立、不落库
    │   ├── 临时 Agent            # 现有 Agent 类
    │   ├── 独立 Runtime
    │   └── 独立 ProcessManager
    └── ChildSession B
        ├── 临时 Context
        ├── 临时 Agent
        ├── 独立 Runtime
        └── 独立 ProcessManager
```

每个子 Agent：

- 继承主 Agent 的角色身份、LLM 配置和基础 Tool 集合。
- 不从 Agent Profile 列表选择新的角色。
- 创建时接收一个任务说明，将其作为子 Context 的首条用户消息。
- 使用独立 Context，不把内部消息、工具调用和工具结果写入主 Context。
- 完成后由 `subagent` Tool 返回结果摘要，主 Agent 决定如何继续。
- 同一时间只能执行一个任务。
- 任务完成后进入 `IDLE`，在 TTL 内可以被再次调用并保留 Context。
- TTL 到期、显式停止或父 Session 关闭后销毁。

### 3.1 主 Context 与子 Context

子 Context 不与主 Context 共享对象，也不自动合并。子 Agent 的内部过程可能包含大量工具协议项和中间结果，直接共享会污染主 Agent 的正式上下文。

数据流固定为：

```text
主 Agent 调用 subagent(task)
    -> 子 Agent Context 追加 task
    -> 子 Agent 独立执行
    -> 子 Agent 返回结果摘要
    -> subagent ToolResult 写入主 Context
```

主 Agent 只看到 ToolResult 中的结果；用户可以通过 UI 的只读入口查看子 Agent Context。

### 3.2 身份和权限 Session

`ChildSession` 的临时 `child_id` 只用于内存管理、UI 查询和权限响应路由。

由于当前 `Context`、`ExecutionContext`、`Tools` 和 `PermissionManager` 要求权限请求使用同一个正式 Session ID，子 Agent 创建时使用以下身份关系：

- 子 Context 的 `session_id` 使用父正式 Session ID。
- 子 Agent 的 `ExecutionContext.session_id` 使用父正式 Session ID。
- 子 Agent 的 `ExecutionContext.agent_id` 使用当前逻辑 Agent ID。
- `PermissionManager` 复用父正式 Session 的实例。
- `child_id` 不传入 Runtime，也不用于构造 PermissionRequest。

这样可以复用当前权限校验和 `once/session` 规则，不需要第二套权限归属模型。每个子 Agent 仍拥有独立 Context、Runtime 状态和 ProcessManager。

## 4. 核心设计

### 4.1 不新增 Agent 类型

子 Agent 使用现有 `Agent` 类，由 Session 层调用已有的 `AgentFactory.load()` 创建：

```python
agent = agent_factory.load(
    parent_agent_id,
    context=child_context,
    execution_context=child_execution_context,
    permission=parent_permission,
    permission_mode=parent_session.permission_mode,
)
```

这里的 `parent_agent_id` 只表示继承持久化配置，不表示复用主 Agent 实例。主 Agent 和每个子 Agent 都是独立内存对象。

子 Agent 不注册 `subagent` Tool，因此第一版不会产生孙 Agent 或递归 Agent 树。

### 4.2 Context 直接使用现有类

创建子 Agent 时直接实例化现有 `Context`：

```python
child_context = Context(context_summarizer_llm, session_id=parent_session_id)
```

不调用 `ContextService`，不恢复数据库时间线，不保存 Context 快照。Context 的追加、压缩、精简、`export()` 和模型输入构建继续使用现有实现。

子 Context 销毁时只解除 `ChildSession` 对它的引用。若需要保留结果，只保存受长度限制的任务结果摘要，不保存完整 Context。

### 4.3 Agent 创建位置

正式 Session 和子 Session 都由 Session 层负责创建 Agent：

```text
SessionService / SessionExecution
    -> 创建 Context
    -> 准备 ExecutionContext、PermissionManager、ProcessManager
    -> 调用 AgentFactory.load()
    -> 得到完整 Agent

Agent
    -> 创建并持有 Runtime
```

Session 层不直接创建 Runtime。子 Session 只复用已有 AgentFactory 的加载能力，不新增 Runtime Factory。

### 4.4 子任务执行

`ChildSessionManager` 在后台线程消费子 Agent 的同步 Generator：

```text
锁内：校验 child 状态并切换为 RUNNING
锁外：消费 agent.run() 事件
锁内：保存状态、结果或 pending 权限
```

不能在持有 Manager 锁时执行 LLM 请求、工具调用或等待进程。

子 Agent 产生 `PermissionRequiredEvent` 后，Manager 保存事件和任务状态，子任务进入 `WAITING_PERMISSION`。用户确认后调用：

```python
child.agent.resolve_permission(response)
```

不向 Runtime 或 Agent 传入 Context。

### 4.5 主 Agent 与子 Agent 的交互

第一版只允许主 Agent 通过 `subagent` Tool 操作子 Agent。用户不直接向子 Agent 发送消息。

建议 Tool 动作：

| action | 参数 | 作用 |
| --- | --- | --- |
| `spawn` | `task`，可选 `name` | 创建并立即启动子 Agent |
| `run` | `child_id`、`task` | 复用空闲子 Agent 执行新任务 |
| `list` | 无 | 列出当前父 Session 中尚未销毁的子 Agent |
| `status` | `child_id` | 查询状态、任务和结果摘要 |
| `wait` | `child_id`，可选 `timeout` | 在本地最大时限内等待结果 |
| `inspect` | `child_id` | 获取截断后的只读 Context |
| `stop` | `child_id` | 停止并销毁子 Agent |

`spawn` 返回 `child_id` 后，主 Agent 可以继续执行其他工作，也可以通过 `wait` 获取结果。第一版不增加父子事件总线、回调总线或独立 SSE。

## 5. 临时对象和状态

### 5.1 ChildSession

新增轻量内存对象，建议路径为 `code/agent/session/child_session.py`。

建议字段：

| 字段 | 说明 |
| --- | --- |
| `child_id` | 临时管理 ID |
| `parent_session_id` | 正式父 Session ID |
| `agent_id` | 继承的逻辑 Agent ID |
| `display_name` | UI 展示名称 |
| `agent` | 完整的现有 Agent 实例 |
| `context` | 独立的现有 Context 实例 |
| `process_manager` | 子 Session 独立 ProcessManager |
| `status` | 当前生命周期状态 |
| `task_id` | 当前任务 ID |
| `task_prompt` | 当前任务说明 |
| `result` | 长度受限的结果摘要 |
| `error` | 稳定错误码和消息 |
| `pending_permission` | 当前待确认权限事件 |
| `created_at` | 创建时间 |
| `last_activity_at` | 最近活动时间 |
| `idle_deadline` | 空闲销毁时间 |

`ChildSession` 不复用 `storage.types.Session`，不进入 Repository，也不包含数据库字段。

### 5.2 状态

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
IDLE -> RUNNING
FAILED -> RUNNING
IDLE/FAILED -> STOPPING -> DESTROYED
任意非 DESTROYED 状态 -> DESTROYED（父 Session 关闭）
```

约束：

- `RUNNING` 和 `WAITING_PERMISSION` 不能被复用。
- `WAITING_PERMISSION` 不计算 idle TTL。
- 成功任务进入 `IDLE`，失败任务进入 `FAILED`；两者都开始计算 TTL。
- 复用时保留 Context，但生成新的 `task_id`。
- `DESTROYED` 是终态，不能重新激活。
- 一个 child 同时只能存在一个任务。

### 5.3 ChildSessionManager

新增 `code/agent/session/child_session_manager.py`，由正式 `SessionExecution` 持有。

职责：

- 保存当前父 Session 的 child 字典。
- 创建 ChildSession 并调用 AgentFactory 创建完整 Agent。
- 后台消费 `Agent.run()` 和 `Agent.resolve_permission()` 的事件流。
- 管理状态、任务、结果、错误和 pending 权限。
- 提供 list、status、wait、inspect、run、stop。
- 创建和销毁 child 专属 ProcessManager。
- 管理 idle TTL、最大 child 数和 worker 数量。
- 父 Session 关闭时停止并销毁所有 child。

不负责：

- 创建正式数据库 Session。
- 访问 ContextService 或任何 Context Repository。
- 重新实现 Agent Loop。
- 创建 Runtime、LLM 或 Tools。
- 加载 AgentProfile 或自行解释 Agent 配置。

建议接口：

```python
class ChildSessionManager:
    def spawn(self, task: str, *, name: str | None = None) -> ChildSummary: ...
    def run(self, child_id: str, task: str) -> ChildSummary: ...
    def list(self) -> list[ChildSummary]: ...
    def status(self, child_id: str) -> ChildSummary: ...
    def wait(self, child_id: str, timeout: float | None = None) -> ChildSummary: ...
    def inspect(self, child_id: str) -> list[dict]: ...
    def resolve_permission(self, child_id: str, response: PermissionResponse) -> None: ...
    def stop(self, child_id: str) -> None: ...
    def close(self) -> None: ...
```

`wait()` 必须有默认和最大本地 timeout，不能无限阻塞主 Agent 的 Tool 调用。

### 5.4 SessionExecution 的持有关系

`SessionExecution` 是正式 Session 的运行时入口，应持有一个 `ChildSessionManager | None`：

- `DIRECT` Session 创建 Manager。
- `GROUP` Session 不创建 Manager，也不注册 `subagent` Tool。
- 正式 Session 关闭时调用 Manager.close()。
- Web API 获取正式 Session 运行时对象时，必须复用同一个打开态 `SessionExecution`，不能每次请求都新建 Manager。
- SessionService 负责打开态 Session 的缓存和关闭；Manager 不自行访问数据库寻找父 Session。

如果现有 Web 服务每次请求都会重新调用 `SessionService.load()`，施工阶段必须先补齐打开态 Session 复用机制，否则后台 child 会在下一次请求中丢失。这是 Session 生命周期问题，不通过持久化 child 解决。

## 6. 权限继承和透传

### 6.1 权限继承

子 Agent 使用父 Session 的：

- `PermissionManager` 实例。
- `permission_mode`。
- `project_path`。
- Session 权限规则。
- 硬安全策略和受保护资源策略。

子 Agent 不拥有独立权限模式、工作目录或权限规则。

`subagent` Tool 只是内存编排，不访问文件、不执行 Shell，不需要新增 `PermissionAction.SUBAGENT_MANAGE`。真正的文件和 Shell 操作仍由子 Agent 调用基础 Tool 时检查父 Session 权限。

### 6.2 权限请求路由

Manager 保存 child 产生的 `PermissionRequiredEvent`，并向主会话返回：

```text
parent_session_id
child_id
task_id
call_id
PermissionRequest
```

用户确认接口必须校验：

- child 属于当前父 Session。
- child 当前状态为 `WAITING_PERMISSION`。
- `call_id` 与 pending 请求一致。
- child 没有被停止或销毁。

校验通过后：

```text
用户 response
    -> ChildSessionManager.resolve_permission(child_id, response)
    -> child.agent.resolve_permission(response)
    -> child Runtime 继续执行
```

`once`、`session`、`deny` 和 `don't ask` 继续沿用当前权限系统。子 Agent 不能绕过父 Session 的硬黑名单、工作目录和权限模式。

多个 child 可以同时处于 `WAITING_PERMISSION`。pending 请求必须保存在对应 ChildSession 内，不能放进父 Session 的单一 active permission 字段中。

## 7. Tool 改动

### 7.1 新增 subagent Tool

建议路径：

```text
code/agent/tools/orchestration/__init__.py
code/agent/tools/orchestration/subagent.py
```

基础 `tools` 根目录仍只保留基础工具入口，子 Agent 编排逻辑放在 `orchestration` 目录。

Tool 通过创建函数绑定当前正式 Session 的 Manager，不查全局对象：

```python
def create_subagent_tool(manager: ChildSessionManager) -> Tool:
    ...
```

约束：

- 不接受 `agent_id`，只能继承当前主 Agent。
- 不接受 `workspace_path` 或 `permission_mode`。
- 不接受父 `session_id`，父关系由绑定的 Manager 确定。
- 子 Runtime 不注册该 Tool。
- task、name、result、inspect 和 wait 都有本地长度或时间上限。

### 7.2 空工作目录

当前 `Tools.prepare_call()` 在查找具体 Tool 后统一检查 workspace。为了允许空项目对话调用不依赖文件系统的 `subagent` Tool，需要给 `Tool` 增加最小元数据：

```python
requires_workspace: bool = True
```

`subagent` 设置为 `False`；`read`、`write`、`edit`、`bash` 和其他项目工具保持默认 `True`。`Tools.prepare_call()` 只在目标 Tool 要求 workspace 时返回 `PROJECT_NOT_SELECTED`。

## 8. Session 组装改动

修改范围限制在 `code/agent/session/session_service.py` 和正式 Session 运行时对象：

1. `SessionExecution` 在 `DIRECT` 模式创建并持有 ChildSessionManager。
2. 为 child 创建 Context、ExecutionContext 和独立 ProcessManager。
3. 通过已有 `AgentFactory.load()` 创建 child Agent。
4. child 的 Context 和 ExecutionContext 使用父正式 Session ID，以便复用父 PermissionManager。
5. parent Agent 创建完成后注册绑定当前 Manager 的 `subagent` Tool。
6. child Agent 只注册原有基础 Tool，不注册 `subagent`。
7. `GROUP` Session 不创建 ChildSessionManager，也不暴露 `subagent` Tool。
8. 正式 Session `close()` 时销毁 Manager。
9. SessionService 复用同一打开态 SessionExecution，保证 child 生命周期跨越多次 API 请求。

不得在 SessionService 中新增直接 Runtime 组装函数。SessionService 只准备 AgentFactory 所需的 Context、ExecutionContext、PermissionManager 和 Tool 定义，再调用 AgentFactory。

## 9. Web API 和 UI

### 9.1 服务端接口

建议新增：

```text
GET  /api/sessions/{session_id}/subagents
GET  /api/sessions/{session_id}/subagents/{child_id}
GET  /api/sessions/{session_id}/subagents/{child_id}/context
POST /api/sessions/{session_id}/subagents/{child_id}/permission
POST /api/sessions/{session_id}/subagents/{child_id}/stop
```

不提供用户向 child 发消息的接口：

```text
POST /api/sessions/{session_id}/subagents/{child_id}/messages
```

所有 child 查询和操作必须通过当前父 Session 的 `SessionExecution` / `ChildSessionManager` 完成，不直接查询 child 数据库记录。

接口必须校验：父 Session 存在且为 `DIRECT`、打开态对象与父 ID一致、child 属于父 Session、child 尚未销毁、权限响应的 call ID 与 pending 请求一致。

### 9.2 前端交互

建议目录：

```text
client/web/front/src/features/subagents/
├── api.ts
├── components/SubagentPanel.tsx
├── components/SubagentContextView.tsx
└── components/SubagentStatus.tsx
```

UI 行为：

- 宽屏在主会话右上区域显示存活 child 的悬浮面板。
- 窄屏隐藏面板，不遮挡消息和输入框；后台任务继续执行。
- 展示 child 名称、任务摘要、状态和等待权限提示。
- 点击 child 后只读查看 Context，不显示输入框、发送按钮或编辑操作。
- 权限弹窗显示来源 child 名称、任务摘要、工具名称和资源。
- child 销毁后从列表移除。

轮询策略：运行中或等待权限时每 1-2 秒查询；全部空闲或失败时降为 5-10 秒，页面不可见时停止高频轮询，切换父 Session 后取消旧查询。

第一版不增加 child 专属 SSE 或内部事件总线。

## 10. 开发阶段

### 阶段 0：冻结正式 Session 契约

**目的**：确保子 Agent 开发不改变当前 Agent、Runtime、Context 和权限契约。

**工作内容**：

- 记录 Python、Web 服务端和前端测试基线。
- 补充 Agent 已绑定 Context 后调用 `run()` 的测试。
- 补充 `Agent.resolve_permission(response)` 的恢复测试。
- 验证每次打开正式 Session 都创建独立 Agent，GROUP 成员共享 Context 对象。
- 明确正式数据库表不会出现 child 数据。

**禁止改动**：`Runtime.run()`、`Runtime.resolve_permission()` 不能回退到接收 Context。

**验收**：全量测试通过，阶段 0 不新增子 Agent 生产代码。

### 阶段 1：临时 ChildSession 生命周期

**目的**：只实现内存 child 的创建、执行状态和销毁，不接主 Agent Tool、API 和 UI。

**新增**：

- `code/agent/session/child_session.py`
- `code/agent/session/child_session_manager.py`
- `tests/session/test_child_session_manager.py`

**工作内容**：创建状态对象；使用注入的 Agent 创建函数得到完整 Agent；后台消费 `agent.run()`；实现 spawn/run/status/wait/inspect/stop/close；每个 child 创建独立 ProcessManager；实现锁、worker 上限和 idle TTL。

**验收**：两个 child 的 Agent、Context、Runtime 状态和进程管理互不影响；运行中和等待权限的 child 不可复用或销毁；空闲/失败 child 按 TTL 销毁；停止后释放 Runtime、Context、Timer 和进程引用；不访问 ContextService、不修改正式数据库。

**依赖**：阶段 0。

### 阶段 2：Session 组装和 subagent Tool

**目的**：让正式 DIRECT Session 的主 Agent 能创建和使用 child。

**修改**：

- `code/agent/session/session_service.py`
- Agent 的 Tool 注册入口（仅在确有必要时）
- `code/agent/tools/types.py`
- `code/agent/tools/tools.py`

**新增**：

- `code/agent/tools/orchestration/__init__.py`
- `code/agent/tools/orchestration/subagent.py`
- 对应 Tool 和 Session 测试

**工作内容**：SessionExecution 持有 Manager；用 AgentFactory.load() 创建 child；parent Agent 额外注册 subagent，child 不注册；GROUP 不注册；实现参数校验和稳定 ToolResult；增加 `requires_workspace`。

**验收**：主 Agent 可以完成 spawn/list/status/wait/inspect/run/stop；GROUP 和 child 不能调用 subagent；无 workspace 的 Session 可以调用 subagent，而 child 调文件工具仍返回 `PROJECT_NOT_SELECTED`；child Context 不进入主 Context 或数据库；AgentFactory、Agent、Runtime 没有子 Agent 专用执行分支。

**依赖**：阶段 1。

### 阶段 3：权限请求透传

**目的**：让 child 使用父 Session 权限，并由主会话完成确认。

**工作内容**：Manager 捕获 `PermissionRequiredEvent`；保存 child、task、call ID 和 pending 请求；实现 `resolve_permission(child_id, response)`；使用 `child.agent.resolve_permission(response)` 恢复；校验父、child、call ID 和状态；验证 once/session/deny/don't ask 和多 child 并发等待。

**明确不改**：不修改 Runtime 权限协议，不新增 `SUBAGENT_MANAGE`，不新增 child PermissionManager、`execution_id` 或第二套权限规则。

**验收**：child 不能绕过父 Session 的 workspace、plan/build/yolo、硬黑名单和 Session 规则。

**依赖**：阶段 2。

### 阶段 4：服务端 API 和只读 UI

**目的**：让用户查看 child 状态、Context 并处理权限请求。

**工作内容**：新增列表、详情、Context、权限和停止接口；添加父子归属校验；增加右上角 child 面板和只读 Context 视图；复用权限弹窗；实现分级轮询；窄屏隐藏面板。

**验收**：API 只能操作当前父 Session 的 child；UI 不能向 child 发消息；状态和权限恢复正确；刷新不会把 child 变成正式历史会话。

**依赖**：阶段 3。

### 阶段 5：生命周期收口和回归验证

**目的**：处理资源清理、服务关闭和边缘场景。

**工作内容**：服务退出时关闭 SessionService 和打开态 SessionExecution；正式 Session 关闭时销毁 Manager；覆盖 LLM/Tool 失败、权限等待时停止、TTL 竞态、重复 stop、打开态 Session 缓存和资源释放；更新架构及持久化文档。

**验收**：Python、Web 服务端、前端测试和浏览器宽窄屏验证通过；没有 child 数据进入正式表；没有后台线程、Timer 或子进程残留。

**依赖**：阶段 4。

## 11. 稳定错误码

至少提供：

```text
SUBAGENT_UNSUPPORTED_SESSION_MODE
SUBAGENT_NOT_FOUND
SUBAGENT_BUSY
SUBAGENT_DESTROYED
SUBAGENT_PERMISSION_PENDING
SUBAGENT_PERMISSION_MISMATCH
SUBAGENT_ALREADY_STOPPED
SUBAGENT_LIMIT_REACHED
SUBAGENT_WAIT_TIMEOUT
SUBAGENT_INVALID_ARGUMENT
SUBAGENT_INTERNAL_ERROR
```

错误消息不能包含堆栈、API Key、数据库路径、Runtime 对象或其他不必要的 Session 数据。

## 12. 资源限制

集中管理以下本地限制：

- 每个正式 Session 最大 child 数和 worker 数量。
- task、child 名称和结果摘要最大字符数。
- `inspect` 最大消息数和字符数。
- `wait` 默认和最大 timeout。
- idle TTL。

这些是本地限制，不依赖第三方 LLM 服务端限制。

## 13. 第一版明确不做

- GROUP Session 中创建子 Agent。
- OPEN / Stanford Town 式自由对话。
- 孙 Agent 或递归 Agent 树。
- 从 Agent Profile 列表选择其他角色。
- 子 Agent 独立 workspace、权限模式或权限规则。
- 子 Session 数据库持久化和进程重启恢复。
- 用户直接向子 Agent 发送消息。
- 自动把子 Context 合并到主 Context。
- 修改 Runtime 的 `run()` / `resolve_permission()` 接口。
- 新增 Runtime Factory、TransientContextService、Context 存储抽象或 ParentSessionBridge。
- 为 child 增加独立 SSE 或内部事件总线。

## 14. 主要风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 主 Agent 与 child 共用 Runtime | 高 | 每个 child 通过 AgentFactory 创建独立 Agent，Agent 自己创建独立 Runtime |
| SessionService 每次请求重新打开 Session | 高 | 缓存打开态 SessionExecution，确保 Manager 跨请求存活 |
| child 使用错误 Context 身份 | 高 | Context 和 ExecutionContext 都使用父正式 Session ID，用 child_id 做内存路由 |
| 子权限响应恢复错误 child | 高 | parent_session_id + child_id + call_id + 状态校验 |
| 子 Context 写入正式时间线 | 高 | child 不创建 ContextService，不调用正式 Repository |
| child 递归创建孙 Agent | 高 | child Agent 不注册 subagent Tool |
| TTL 与任务结束同时修改状态 | 中 | RLock、状态校验和幂等销毁 |
| child 进程残留 | 高 | 每个 child 使用独立 ProcessManager，销毁时 stop_all |
| 空 workspace 无法调用 subagent | 中 | Tool 增加 `requires_workspace` 能力声明 |
| UI 轮询过密 | 中 | 运行态快速轮询，空闲态降频，页面隐藏时暂停 |
| inspect 返回过多内容 | 中 | 按消息数和字符数双重截断 |

## 15. 完成检查清单

### 架构与 Agent

- [ ] 子 Agent 使用现有 `Agent` 类，不新增 Agent 类型。
- [ ] 子 Agent 由 Session 层创建，Agent 自己创建 Runtime。
- [ ] 每个 child 拥有独立 Agent、Context、Runtime 和 ProcessManager。
- [ ] Runtime 的 `run()` 和 `resolve_permission()` 接口没有变化。
- [ ] child Agent 没有 subagent Tool。
- [ ] 同一个 child 不能同时执行两个任务。

### Context 与持久化

- [ ] child Context 使用现有 Context 类。
- [ ] child Context 不调用 ContextService。
- [ ] 没有 TransientContextService 或临时 Repository。
- [ ] child 创建、运行、完成和销毁均不写正式业务表。
- [ ] child Context 只在生命周期内保留，销毁后释放引用。
- [ ] 子结果通过 ToolResult 返回主 Context，而不是自动合并 Context。

### 权限

- [ ] child 复用父 PermissionManager。
- [ ] child Context 和 ExecutionContext 使用父正式 Session ID。
- [ ] plan/build/yolo 行为与父 Session 一致。
- [ ] once/session/deny/don't ask 语义保持不变。
- [ ] 多 child 权限请求不会串线。
- [ ] 等待权限期间不会触发 idle TTL。

### 生命周期与 Tool

- [ ] spawn、run、list、status、wait、inspect、stop 可用。
- [ ] 空 workspace 可以调用 subagent。
- [ ] child 调用基础文件工具时仍正确要求 workspace。
- [ ] idle child 可以复用并保留 Context。
- [ ] TTL、显式 stop 和父 Session 关闭都能销毁 child。
- [ ] child 后台进程随 child 销毁而停止。

### Web UI

- [ ] 宽屏显示右上角 child 面板。
- [ ] 窄屏不遮挡消息和输入框。
- [ ] Context 查看只读且没有输入框。
- [ ] 主会话可以处理 child 权限请求。
- [ ] child 不出现在正式历史会话列表。

## 16. 建议提交顺序

```text
test: freeze current agent and session contracts
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
- 如果实际施工发现必须修改 Runtime、Context 或新增存储层，先更新本计划并说明现有接口为何无法满足。
