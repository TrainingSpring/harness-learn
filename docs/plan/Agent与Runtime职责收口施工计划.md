# Agent 与 Runtime 职责收口施工计划

> 状态：已施工。
>
> 本计划是独立的架构收口计划，不属于《子 Agent 开发迭代计划（未施工）》，也不表示子 Agent 功能开始施工。

施工结果：阶段 0 至阶段 7 已完成。核心提交为 `35f9789` 和 `8ee92a2`；文档收口由后续文档提交完成。

## 1. 文档目的

当前 `Agent` 只是由 `AgentFactory` 从数据库配置转换出来的数据对象，真正的 LLM、Tools、ExecutionContext、权限和 Runtime 都由 `SessionService` 再次组装。这导致：

1. `Agent` 直接持有 storage 层的 `AgentProfile`，运行时领域对象依赖持久化数据结构。
2. `Agent` 没有实际执行能力，只是 Runtime 组装前的中间数据。
3. `SessionService` 同时负责 Session 生命周期、Context 持久化、Agent 配置解释和 Runtime 组装，职责过重。
4. `Runtime.run(context)` 和 `Runtime.resolve_permission(context, response)` 要求每次调用都再次传入 Context，虽然一个 Runtime 实例实际只服务于一个 Session 中的一个 Agent 实例。
5. `PromptBuilder` 面向 `AgentProfile`，使提示词构建依赖 storage 层，而不是面向真正执行任务的 Agent。

本计划把结构收口为：

```text
SessionService / SessionExecution
├── 创建、恢复、持久化 Session 共享 Context
├── 创建 Session 级 PermissionManager 和 ProcessManager
├── 为每个固定成员创建独立 Agent 实例
└── 负责 DIRECT / GROUP 调度

Agent
├── 身份和角色字段
├── 当前 Session 的 Context 引用
├── LLM
├── Tools
├── ExecutionContext
├── PermissionManager 引用
└── Runtime

Runtime
└── 只负责一个 Agent 实例内部的 Agent Loop、工具调用和权限暂停/恢复
```

## 2. 最终架构结论

### 2.1 实例边界

1. 每个打开的 Session 都实例化自己的 Agent 对象。
2. 同一个逻辑 Agent ID 可以同时出现在多个 Session 中，但对应不同的内存 Agent 实例。
3. 不再跨 Session 复用 Agent 实例，也不设计 Agent 空闲池。
4. 每个 Agent 实例拥有独立 Runtime、LLM、Tools 和 ExecutionContext。
5. 一个 Session 只有一个 Context。
6. GROUP 中的所有 Agent 实例持有同一个 Context 对象引用。
7. GROUP 仍由 SessionExecution 顺序调度，第一版不允许多个 Agent 并发修改共享 Context。

### 2.2 Context 的“创建者”和“持有者”

Context 的职责需要区分为两层：

- Session 是 Context 的生命周期与持久化所有者：负责创建、恢复、保存和销毁。
- Agent 是 Context 的运行时持有者：构造时接收 Context，并把它交给自己创建的 Runtime 使用。
- Runtime 只保存该 Context 的引用并执行 Loop，不创建 Context、不恢复 Context、不访问数据库。

因此，“Agent 拥有 Context”不代表 Agent 负责 Context 持久化；它表示 Agent 是一个可以直接运行的完整对象，不需要 Session 在每次调用时重新传入 Context。

### 2.3 Agent 的完整职责

Agent 不再是数据结构，而是一个完整的执行对象，包含：

- `agent_id`
- `name`
- `description`
- `personality`
- `expertise`
- `llm_config`
- `tool_definitions`
- `context`
- `execution_context`
- `permission`
- `llm`
- `tools`
- `runtime`

Agent 对外提供：

```python
def run(self) -> Generator[RuntimeEvent, None, None]: ...
def resolve_permission(
    self,
    response: PermissionResponse,
) -> Generator[RuntimeEvent, None, None]: ...
def cancel(self) -> None: ...
```

这三个方法只委托给 Agent 内部 Runtime，不在 Agent 再实现一套 Loop。

### 2.4 Runtime 的完整职责

Runtime 保留：

- LLM 流式调用。
- Agent Loop。
- 模型输出写入 Context。
- function call 准备和执行。
- 权限检查、暂停和恢复。
- Tool Result 写入 Context。
- Runtime 状态、pending permission 和 tool queue。

Runtime 不再负责：

- 接收或切换任意 Context。
- Session 创建、恢复或持久化。
- DIRECT / GROUP 成员选择。
- Agent 配置加载。
- Runtime 之外的 Agent 身份与角色描述。

### 2.5 Session 的完整职责

SessionService / SessionExecution 保留：

- 创建或恢复持久化 Session。
- 创建并恢复唯一共享 Context。
- 创建 Session 级 PermissionManager。
- 创建 SessionProcessManager。
- 创建每个固定成员的 ExecutionContext。
- 通过 AgentFactory 为每个成员实例化完整 Agent。
- 保存原始 ContextItem 和当前 Context 快照。
- DIRECT / GROUP 调度。
- 记录当前等待权限的成员位置。
- 在 workspace 或 permission mode 变化后重新创建成员 Agent。

Session 不再创建成员 Agent 内部的 Runtime、LLM 或 Tools；Context 专用的
summarizer LLM 仍由 Session 在创建共享 Context 时单独准备。

### 2.6 storage 边界

`storage.types.AgentProfile` 继续存在，但只表示数据库记录。它可以包含：

- `id`
- `name`
- `description`
- `personality`
- `expertise`
- `llm_profile_id`
- `tools`
- `is_enabled`
- 创建和更新时间等持久化字段

运行时 `Agent` 不得保存 `AgentProfile`，也不得导入 storage 层类型。

`AgentFactory` 是 storage 到 runtime 的唯一映射边界：读取 AgentProfile、LLMProfile 和工具名称，再把必要字段显式传给 Agent。

## 3. 明确不做的事项

本计划不做以下工作：

1. 不新增 `AgentDefinition`、`StableAgent` 或另一种 Profile 类型。
2. 不新增 `SessionAgentRuntimeFactory` 或独立 Runtime Factory。
3. 不保留 `Runtime.run(context)` 的兼容重载。
4. 不保留 `Runtime.resolve_permission(context, response)` 的兼容重载。
5. 不让 Agent 访问 Repository、ContextService 或数据库。
6. 不改变 Session、AgentProfile 或 ContextItem 的数据库表结构。
7. 不改变 DIRECT / GROUP 的产品语义和现有调度顺序。
8. 不开始实现子 Agent。
9. 不为了未来可能复用 Agent 而增加状态池、租约或空闲检测。

## 4. 当前实现与目标差异

| 模块 | 当前实现 | 目标实现 | 修改原因 |
| --- | --- | --- | --- |
| `Agent` | frozen dataclass，保存 `AgentProfile`、LLMConfig、工具定义 | 完整运行对象，保存显式角色字段、Context、LLM、Tools、权限和 Runtime | 去掉 storage 耦合，让 Agent 可以直接执行 |
| `AgentFactory` | `load(agent_id)` 返回稳定数据对象 | `load(...)` 接收 Session 依赖并返回完整 Agent | Factory 成为唯一配置映射和 Agent 组装入口 |
| `PromptBuilder` | `build(AgentProfile, ...)` | `build(Agent, ...)` | 提示词服务于实际 Agent，而不是数据库记录 |
| `LLMConfig` | 包含预构建的 `instructions` | 只包含 `base_url`、`api_key`、`model` | instructions 是 Agent + Session 权限派生结果，不是连接配置 |
| `Runtime` | 构造时没有 Context，`run/resolve_permission` 每次传 Context | 构造时绑定 Context，`run()` 和 `resolve_permission(response)` 无 Context 参数 | 一个 Runtime 只属于一个 Agent 实例，不应支持任意切换 Context |
| `SessionExecution` | 保存 `runtimes` 和 `refresh_runtimes` | 保存 `agents` 和 `refresh_agents` | Session 调度 Agent，不直接操作 Agent 内部 Runtime |
| `SessionService` | 负责创建 LLM、Tools 和 Runtime | 只准备 Session 级依赖并调用 AgentFactory | 收缩 Session 的组装职责 |
| CLI | 手动创建 Profile、Agent、Tools、Runtime，并直接调用 Runtime | 创建完整 Agent，只调用 Agent API | CLI 与正式 Session 使用同一对象边界 |

## 5. 目标接口

### 5.1 LLMConfig

文件：`code/agent/head/types.py`

目标：

```python
@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
```

处理规则：

1. 删除 `instructions` 字段。
2. `LLMConfig` 只表达建立 LLM 连接所需的数据。
3. Agent 的系统指令由 `PromptBuilder.build(agent, permission_mode=...)` 动态生成。
4. Context 的 summarizer LLM 使用独立 LLM 实例，不能复用 Agent 的 LLM，因为 Context 会设置压缩专用 system prompt。

### 5.2 Agent

文件：`code/agent/runtime/agent.py`

建议从 frozen dataclass 改为普通类。目标构造接口：

```python
class Agent:
    def __init__(
        self,
        *,
        agent_id: str,
        name: str,
        description: str,
        personality: str,
        expertise: tuple[str, ...],
        llm_config: LLMConfig,
        tool_definitions: tuple[Tool, ...],
        context: Context,
        execution_context: ExecutionContext,
        permission: PermissionManager,
        permission_mode: str,
        prompt_builder: PromptBuilder | None = None,
    ) -> None:
        ...
```

构造顺序固定为：

```text
保存身份字段和 Session 注入依赖
    ↓
创建 Tools(execution_context) 并注册 tool_definitions
    ↓
PromptBuilder.build(self, permission_mode=...)
    ↓
创建 Agent 自己的 LLM
    ↓
创建 Runtime(llm, tools, execution_context, permission, context)
```

约束：

- `context.session_id` 必须等于 `execution_context.session_id`。
- `agent_id` 必须等于 `execution_context.agent_id`。
- `expertise` 和 `tool_definitions` 使用不可变 tuple，避免实例外部修改配置。
- Agent 不允许接收 `AgentProfile`。
- Agent 不访问数据库。
- Agent 的 `run()`、`resolve_permission()` 和 `cancel()` 只代理内部 Runtime。

### 5.3 PromptBuilder

文件：`code/agent/runtime/prompt_builder.py`

目标接口：

```python
def build(
    self,
    agent: "Agent",
    session_context: str | None = None,
    tools: list[str] | None = None,
    permission_mode: str | None = None,
) -> str:
    ...
```

实现要求：

1. 删除 `from storage.types import AgentProfile`。
2. 使用 `TYPE_CHECKING` 和字符串注解引用 Agent，避免 `Agent -> PromptBuilder -> Agent` 运行时循环导入。
3. 默认工具名从 `agent.tool_definitions` 或已经注册的 `agent.tools` 获取。
4. 角色字段只读取 Agent 的 `name`、`description`、`personality` 和 `expertise`。
5. 保留现有 plan/build/yolo 提示词语义。

### 5.4 Runtime

文件：`code/agent/runtime/runtime.py`

目标接口：

```python
class Runtime:
    def __init__(
        self,
        llm: LLM,
        tools: Tools,
        execution_context: ExecutionContext,
        permission: PermissionManager,
        context: Context,
    ) -> None:
        ...

    def run(self) -> Generator[RuntimeEvent, None, None]: ...

    def resolve_permission(
        self,
        response: PermissionResponse,
    ) -> Generator[RuntimeEvent, None, None]: ...
```

内部调整：

- `self.ctx` 重命名为 `self.execution_context`，避免和模型 Context 混淆。
- 新增 `self.context`。
- `call_llm()`、`_run_llm_loop()`、`_record_response_items()`、`_drain_tool_queue()` 和 `_append_tool_result()` 不再传递 Context 参数，统一使用 `self.context`。
- 删除 `_validate_context()`；构造时一次性验证 Context 类型和身份关系。
- `cancel()` 行为保持不变。
- Runtime 仍不访问 ContextService 或 Repository。

### 5.5 AgentFactory

文件：`code/agent/runtime/agent_factory.py`

目标接口：

```python
def load(
    self,
    agent_id: str,
    *,
    context: Context,
    execution_context: ExecutionContext,
    permission: PermissionManager,
    permission_mode: str,
) -> Agent:
    ...

def load_llm_config(self, agent_id: str) -> LLMConfig:
    ...
```

`load_llm_config()` 只用于 Session 创建 Context 的独立 summarizer LLM。增加这个小接口是为了解决组装顺序：Session 必须先创建 Context，Agent 又必须在构造时接收 Context。这里不新增 AgentDefinition，也不让 Session 直接解释 LLMProfile。

Factory 的映射规则：

```text
AgentProfile.id            -> Agent.agent_id
AgentProfile.name          -> Agent.name
AgentProfile.description   -> Agent.description
AgentProfile.personality   -> Agent.personality
AgentProfile.expertise     -> Agent.expertise
LLMProfile 连接字段         -> Agent.llm_config
AgentProfile.tools         -> Agent.tool_definitions
Session 注入参数            -> Context / ExecutionContext / PermissionManager / permission_mode
```

Factory 不再预构建 instructions，不再把 AgentProfile 保存到 Agent。

### 5.6 SessionService 与 SessionExecution

文件：`code/agent/session/session_service.py`

目标字段：

```python
class SessionExecution:
    session: Session
    context: Context
    context_service: ContextService
    members: tuple[SessionAgent, ...]
    agents: dict[str, Agent]
    process_manager: SessionProcessManager
```

替换项：

```text
runtimes         -> agents
refresh_runtimes -> refresh_agents
_create_runtimes -> _create_agents
_create_runtime  -> 删除，由 AgentFactory.load() 取代
```

调用替换：

```text
runtime.run(self.context)                         -> agent.run()
runtime.resolve_permission(self.context, response) -> agent.resolve_permission(response)
runtime.cancel()                                   -> agent.cancel()
```

`SessionService._open()` 的目标顺序：

```text
加载固定成员
    ↓
通过第一位成员的 LLMConfig 创建独立 summarizer LLM
    ↓
创建 Session 唯一 Context
    ↓
ContextService 恢复 Context
    ↓
创建 SessionProcessManager
    ↓
创建一个 Session 共享 PermissionManager
    ↓
为每个成员创建独立 ExecutionContext
    ↓
AgentFactory.load(...) 创建完整 Agent
    ↓
返回保存 agents 的 SessionExecution
```

GROUP 约束：

- `agents[a].context is agents[b].context is session_execution.context`。
- `agents[a].runtime is not agents[b].runtime`。
- `agents[a].tools is not agents[b].tools`。
- `agents[a].execution_context is not agents[b].execution_context`。
- `agents[a].permission is agents[b].permission`，因为权限属于 Session。

workspace 或 permission mode 变化时，SessionExecution 在空闲状态下调用 `refresh_agents`，使用原共享 Context 和原 SessionProcessManager 创建一组新 Agent；不再只替换 Runtime。

### 5.7 CLI

文件：`code/cli/main.py`

目标：

1. 删除 `StableAgent`、手工 AgentProfile 和手工 Runtime 组装。
2. CLI 创建 Context、ExecutionContext、PermissionManager 和显式 Agent 字段，再实例化完整 Agent。
3. `build_runtime()` 改为 `build_agent()`，返回 Agent。
4. `run_agent_events()` 接收 Agent，不接收 Runtime 和 Context。
5. 权限恢复调用 `agent.resolve_permission(response)`。
6. `/tools` 从 `agent.tools.list` 读取。
7. `/clear` 使用 `agent.context.restore([])`。
8. 普通消息先追加到 `agent.context`，再调用 `agent.run()`。

## 6. 文件改动清单

### 6.1 必须修改的生产代码

| 文件 | 修改内容 |
| --- | --- |
| `code/agent/head/types.py` | 收缩 LLMConfig，删除 instructions |
| `code/agent/runtime/agent.py` | 从 storage 数据对象改为完整 Agent；创建 LLM、Tools 和 Runtime；提供执行方法 |
| `code/agent/runtime/runtime.py` | 构造时绑定 Context；删除 run/resolve_permission 的 Context 参数 |
| `code/agent/runtime/agent_factory.py` | 显式映射 storage 字段；注入 Session 依赖；返回完整 Agent |
| `code/agent/runtime/prompt_builder.py` | 从 Agent 构建提示词，删除 AgentProfile 依赖 |
| `code/agent/session/session_service.py` | 从 Runtime 调度改为 Agent 调度，删除 Runtime 组装逻辑 |
| `code/cli/main.py` | 使用完整 Agent API |

### 6.2 必须修改的测试

| 文件 | 修改重点 |
| --- | --- |
| `tests/runtime/test_agent.py` | 验证 Agent 是完整对象、持有 Context、拥有独立 Runtime，并代理执行接口 |
| `tests/runtime/test_agent_factory.py` | 验证 storage 到 Agent 的字段映射及完整组装 |
| `tests/runtime/test_prompt_builder.py` | 改为从 Agent 构建提示词，验证不依赖 AgentProfile |
| `tests/runtime/test_runtime_context_contract.py` | Runtime 构造时绑定 Context，run 无参数 |
| `tests/runtime/test_runtime_persistence.py` | 验证绑定 Context 的消息写入 |
| `tests/runtime/test_runtime_reentrancy.py` | 迁移 run/resolve_permission 调用并保留重入保护 |
| `tests/runtime/test_permission_session_isolation.py` | 验证不同 Session 的 Agent/Runtime/权限等待状态隔离 |
| `tests/runtime/test_runtime_failure_persistence.py` | 测试替身从 FakeRuntime 改为 Agent 边界或 Agent-compatible double |
| `tests/test_runtime_permissions.py` | 迁移 Runtime 构造和权限恢复接口 |
| `tests/session/test_session_execution.py` | 从 FakeRuntime 改为 FakeAgent；验证 GROUP 共享 Context |
| `tests/session/test_session_service.py` | 验证 Session 创建完整 Agent，不再创建裸 Runtime |
| `tests/cli/test_main.py` | 验证 CLI 只调用 Agent API |

### 6.3 回归检查但预计不改公共接口的文件

```text
client/web/server/app/services/chat_service.py
client/web/server/app/services/run_registry.py
client/web/server/tests/test_runs_api.py
client/web/server/tests/test_sessions_api.py
```

Web 层仍通过 SessionExecution 发送消息、恢复权限和取消运行，正常情况下无需感知 `runtimes -> agents` 的内部变化。若测试发现 Web 层直接访问 `runtimes`，必须改为 SessionExecution 的公开方法，不得暴露 Agent 内部 Runtime。

### 6.4 最后更新的文档

```text
docs/plan/上下文与运行时架构更新迭代计划.md
docs/plan/子Agent开发迭代计划（未施工）.md
```

只修正已经过时的架构描述：Agent 将持有 Session 注入的 Context 并拥有 Runtime。子 Agent 计划仍保持“未施工”，不得借本次重构提前实现。

## 7. 分阶段施工

## 阶段 0：冻结基线和最终契约（已完成）

### 目的

在修改接口前固定现有可见行为，并把本计划中的对象关系写成测试断言，防止重构过程中改变消息、权限或持久化语义。

### 工作项

1. 运行全量测试并记录基线数量。
2. 补充或调整 Agent 架构契约测试，先表达最终关系。
3. 固定 DIRECT 单 Agent 的消息流程。
4. 固定 GROUP 的顺序调度和共享 Context 行为。
5. 固定权限暂停、恢复和 cancel 行为。
6. 固定 ContextItem 与 current_context_json 的持久化时机。
7. 用 CodeGraph 重新检查 `Runtime.run`、`Runtime.resolve_permission`、`Agent.profile`、`SessionExecution.runtimes` 和 `LLMConfig.instructions` 的调用面。

### 验收

- [ ] 已记录重构前全量测试结果。
- [ ] 最终对象关系有明确测试，不只依赖类型注解。
- [ ] 已列出所有旧接口调用方。
- [ ] 没有修改运行时行为。

### 验证

```bash
pytest -q
git diff --check
```

### 依赖

无。

## 阶段 1：将 Context 绑定到 Runtime（已完成）

### 目的

先收紧 Runtime 的语义：一个 Runtime 实例从创建到销毁只使用一个 Context，不再支持调用方切换 Context。

### 修改文件

```text
code/agent/runtime/runtime.py
tests/runtime/test_runtime_context_contract.py
tests/runtime/test_runtime_persistence.py
tests/runtime/test_runtime_reentrancy.py
tests/runtime/test_permission_session_isolation.py
tests/test_runtime_permissions.py
```

### 工作项

1. Runtime 构造器新增 Context。
2. `ctx` 参数和字段改名为 `execution_context`。
3. `run(context)` 改为 `run()`。
4. `resolve_permission(context, response)` 改为 `resolve_permission(response)`。
5. 内部所有 Context 参数改为使用 `self.context`。
6. 删除 `_validate_context()`。
7. 构造时验证 Context 与 ExecutionContext 的 session_id 一致。
8. 保持 RuntimeState、pending Tool Call、FIFO Tool Queue 和 cancel 语义不变。
9. 更新直接构造 Runtime 的测试。

### 验收

- [ ] Runtime 创建后不能切换 Context。
- [ ] `run()` 只修改构造时绑定的 Context。
- [ ] 权限恢复继续修改同一个 Context。
- [ ] Runtime 仍不访问数据库。
- [ ] 不存在旧签名兼容分支。

### 验证

```bash
pytest -q tests/runtime/test_runtime_context_contract.py \
  tests/runtime/test_runtime_persistence.py \
  tests/runtime/test_runtime_reentrancy.py \
  tests/runtime/test_permission_session_isolation.py \
  tests/test_runtime_permissions.py
```

### 依赖

阶段 0。

## 阶段 2：把 Agent 收口为完整运行对象（已完成）

### 目的

移除 Agent 对 AgentProfile 的依赖，使 Agent 自己创建并拥有 LLM、Tools 和 Runtime，同时持有 Session 注入的 Context。

### 修改文件

```text
code/agent/head/types.py
code/agent/runtime/agent.py
code/agent/runtime/prompt_builder.py
tests/runtime/test_agent.py
tests/runtime/test_prompt_builder.py
```

### 工作项

1. 从 LLMConfig 删除 instructions。
2. Agent 从 frozen dataclass 改为普通运行类。
3. 把 id、name、description、personality、expertise 提升为 Agent 自身字段。
4. 删除 `profile` 字段和 storage 导入。
5. Agent 接收 Context、ExecutionContext、PermissionManager 和 permission mode。
6. Agent 创建并注册 Tools。
7. PromptBuilder 改为读取 Agent。
8. Agent 创建带动态 instructions 的 LLM。
9. Agent 创建绑定 Context 的 Runtime。
10. Agent 提供 run、resolve_permission 和 cancel。
11. 增加身份一致性校验。

### 验收

- [ ] Agent 模块不导入 storage。
- [ ] Agent 创建完成后可以直接 `run()`。
- [ ] Agent 的 LLM、Tools、Runtime 均已初始化。
- [ ] PromptBuilder 不接收 AgentProfile。
- [ ] LLMConfig 不保存派生 instructions。
- [ ] Agent 不实现第二套 Loop。

### 验证

```bash
pytest -q tests/runtime/test_agent.py tests/runtime/test_prompt_builder.py
python -m compileall -q code/agent/runtime code/agent/head
```

### 依赖

阶段 1。

## 阶段 3：改造 AgentFactory 的 storage 映射（已完成）

### 目的

让 AgentFactory 成为从数据库配置到完整 Agent 的唯一边界，Session 不再解释 AgentProfile 或创建 Agent 内部能力。

### 修改文件

```text
code/agent/runtime/agent_factory.py
tests/runtime/test_agent_factory.py
```

### 工作项

1. 扩展 `load()` 的 Session 注入参数。
2. 显式提取 AgentProfile 的运行时字段。
3. 显式映射 LLMProfile 为不含 instructions 的 LLMConfig。
4. 解析工具名为受信任 Tool 定义。
5. 实例化完整 Agent。
6. 增加 `load_llm_config()`，供 Session 创建独立 summarizer LLM。
7. 统一 Agent 不存在、LLMProfile 不存在、API Key 缺失和工具不存在的错误。
8. 删除 Factory 内的 `PromptBuilder.build(profile)`。

### 验收

- [ ] Factory 返回的 Agent 可以直接运行。
- [ ] Agent 中不存在 AgentProfile 引用。
- [ ] Factory 不创建 Context、不访问 ContextService。
- [ ] Factory 不保存 Session 状态。
- [ ] AgentProfile 变更不会泄漏为运行时可变引用。

### 验证

```bash
pytest -q tests/runtime/test_agent_factory.py tests/runtime/test_agent.py
```

### 依赖

阶段 2。

## 阶段 4：Session 从 Runtime 调度切换为 Agent 调度（已完成）

### 目的

把 Runtime 组装从 SessionService 移除。Session 只创建共享 Context 和 Session 级依赖，再创建并调度完整 Agent。

### 修改文件

```text
code/agent/session/session_service.py
tests/session/test_session_execution.py
tests/session/test_session_service.py
tests/runtime/test_runtime_failure_persistence.py
tests/runtime/test_permission_session_isolation.py
```

### 工作项

1. SessionExecution 的 `runtimes` 改为 `agents`。
2. `refresh_runtimes` 改为 `refresh_agents`。
3. `_drive_from()` 调用 `agent.run()`。
4. 权限恢复调用 `agent.resolve_permission(response)`。
5. cancel 调用活动 Agent 的 `cancel()`。
6. SessionService 使用第一位成员的 LLMConfig 创建独立 Context summarizer。
7. 创建一个 Session 共享 PermissionManager。
8. 为每个成员创建独立 ExecutionContext。
9. 调用 AgentFactory 创建完整 Agent。
10. 删除 `_create_runtime()`。
11. `_create_runtimes()` 改为 `_create_agents()`。
12. workspace 或 permission mode 变化时整体替换 agents。
13. 保持 ContextService 保存边界和 GROUP 调度顺序不变。

### 必须新增的隔离断言

1. 同一个 Agent ID 打开两个 Session，得到不同 Agent 实例。
2. 两个 Session 的 Context、Runtime、LLM、Tools、ExecutionContext 和 pending permission 都不同。
3. 同一 GROUP 内多个 Agent 的 Context 对象完全相同。
4. 同一 GROUP 内多个 Agent 的 Runtime、LLM、Tools 和 ExecutionContext 不同。
5. 同一 GROUP 内多个 Agent 引用同一个 Session PermissionManager。
6. Context 压缩只发生在共享 Context 上，不产生每个 Agent 各自的压缩结果。

### 验收

- [ ] SessionService 不再直接实例化 Runtime。
- [ ] SessionExecution 不公开 runtimes 字典。
- [ ] DIRECT 行为不变。
- [ ] GROUP 共享一份 Context 并顺序运行多个 Agent。
- [ ] 权限暂停后能恢复正确的 Agent。
- [ ] workspace 和 permission mode 更新后 Agent 环境正确刷新。
- [ ] Context 原始事件与当前快照仍正常持久化。

### 验证

```bash
pytest -q tests/session \
  tests/runtime/test_permission_session_isolation.py \
  tests/runtime/test_runtime_failure_persistence.py
```

### 依赖

阶段 3。

## 阶段 5：迁移 CLI 和剩余调用方（已完成）

### 目的

清除 Session 之外对裸 Runtime 的组装和调用，使所有产品入口都使用完整 Agent API。

### 修改文件

```text
code/cli/main.py
tests/cli/test_main.py
```

并按 CodeGraph 影响分析结果处理其他实际调用方。

### 工作项

1. `build_runtime()` 改为 `build_agent()`。
2. 删除 CLI 的 AgentProfile 构造。
3. 删除 CLI 的独立 Runtime 构造。
4. 事件消费函数改为接收 Agent。
5. 工具列表、Context 清空、run、权限恢复全部经过 Agent。
6. 检查 Web Server 是否越过 SessionExecution 访问 runtimes；如有则改用公开 SessionExecution 方法。
7. 扫描并删除所有旧 Runtime 方法签名调用。

### 验收

- [ ] CLI 不直接实例化 Runtime。
- [ ] CLI 不创建 AgentProfile。
- [ ] CLI 的发送、权限恢复和 cancel 只调用 Agent。
- [ ] Web API 对外协议没有变化。
- [ ] 生产代码中不存在 `run(context)`。
- [ ] 生产代码中不存在 `resolve_permission(context, response)`。

### 验证

```bash
pytest -q tests/cli/test_main.py client/web/server/tests
python -m compileall -q code/agent code/cli client/web/server
```

### 依赖

阶段 4。

## 阶段 6：删除旧路径并做架构收口（已完成）

### 目的

删除重构过程中不再需要的字段、导入、命名和测试假设，不留下双轨接口。

### 删除清单

- [ ] `Agent.profile`
- [ ] 运行时模块对 `AgentProfile` 的导入
- [ ] `LLMConfig.instructions`
- [ ] `Runtime.run(context)`
- [ ] `Runtime.resolve_permission(context, response)`
- [ ] `Runtime._validate_context()`
- [ ] `SessionExecution.runtimes`
- [ ] `SessionExecution._refresh_runtimes`
- [ ] `SessionService._create_runtime()`
- [ ] `SessionService._create_runtimes()`
- [ ] CLI 的 `StableAgent` 别名和手工 Runtime 组装
- [ ] 测试中的 FakeRuntime Session 边界
- [ ] 为旧接口保留的注释、类型忽略或兼容分支

### 命名检查

- `context` 只表示模型上下文。
- `execution_context` 只表示工具执行身份和 workspace。
- 不再使用含义不明确的 `ctx` 保存 ExecutionContext。
- Session 层使用 `agents`，Runtime 只作为 Agent 内部字段出现。

### 验收

- [ ] CodeGraph 找不到生产代码中的旧调用关系。
- [ ] `Agent` 模块没有 storage AgentProfile 依赖；仅 `AgentFactory` 作为配置映射边界允许读取 storage 类型。
- [ ] 没有新增 AgentDefinition、Runtime Factory 或兼容 Adapter。
- [ ] 所有测试替身与最终公开边界一致。

### 验证

```bash
pytest -q
python -m compileall -q code/agent code/cli client/web/server
git diff --check
```

### 依赖

阶段 5。

## 阶段 7：更新架构文档和最终回归（已完成）

### 目的

让文档与新实现一致，并证明这次职责迁移没有改变产品行为。

### 工作项

1. 在《上下文与运行时架构更新迭代计划》中注明旧的“Agent 不持有 Context、Runtime.run(context)”结论已被本计划替代。
2. 修正《子 Agent 开发迭代计划（未施工）》中的旧前提，但保持未施工状态。
3. 检查模块 docstring 和公开方法注释。
4. 运行全量 Python 测试。
5. 运行 Web Server 测试。
6. 编译检查 Python 源码。
7. 检查 diff、未跟踪文件和无关改动。

### 最终验收

- [ ] Session 创建和恢复共享 Context。
- [ ] Agent 持有 Context，并拥有 LLM、Tools、ExecutionContext、PermissionManager 和 Runtime。
- [ ] Runtime.run() 不接收 Context。
- [ ] Runtime.resolve_permission() 不接收 Context。
- [ ] 同一逻辑 Agent 在不同 Session 中是不同实例。
- [ ] GROUP 中多个 Agent 共享同一 Context，但不共享 Runtime。
- [ ] Agent 不依赖 storage AgentProfile。
- [ ] PromptBuilder 面向 Agent。
- [ ] Session 不组装裸 Runtime。
- [ ] ContextService 仍只负责持久化，不进入 Agent Loop。
- [ ] DIRECT、GROUP、权限暂停恢复、workspace 更新和 Context 恢复全部通过回归测试。
- [ ] 没有旧接口兼容代码。
- [ ] 子 Agent 功能没有被提前实现。

### 最终验证命令

```bash
pytest -q
python -m compileall -q code/agent code/cli client/web/server
git diff --check
```

### 依赖

阶段 6。

### 实施记录

阶段 7 已完成，实际结果如下：

1. Runtime 已在构造时绑定 Context；生产代码中 `run(context)` 和
   `resolve_permission(context, response)` 均已删除。
2. Agent 已成为完整运行对象，保存显式身份字段、Context、LLM、Tools、
   ExecutionContext、PermissionManager 和 Runtime。
3. AgentFactory 已成为 storage 配置到运行时 Agent 的映射边界；Agent 不再保存
   AgentProfile，PromptBuilder 不再接收 AgentProfile。
4. SessionExecution 已从保存 `runtimes` 改为保存 `agents`；GROUP 成员共享同一
   Context，但各自拥有独立 Runtime、LLM、Tools 和 ExecutionContext。
5. CLI 已迁移到 Agent API，SessionService 不再直接创建成员 Runtime。
6. 子 Agent 计划未施工，未新增子 Agent、临时存储或专用 Runtime 分支。
7. 验证结果：`pytest -q`，289 passed；`python -m compileall -q code/agent code/cli client/web/server`；`git diff --check`。

## 8. 阶段依赖和提交策略

```text
阶段 0：基线与契约
    ↓
阶段 1：Runtime 固定 Context
    ↓
阶段 2：完整 Agent + PromptBuilder + LLMConfig
    ↓
阶段 3：AgentFactory 映射
    ↓
阶段 4：Session 调度 Agent
    ↓
阶段 5：CLI 与剩余调用方
    ↓
阶段 6：删除旧路径
    ↓
阶段 7：文档与全量回归
```

由于 Runtime、Agent、Factory 和 Session 的接口存在连续依赖，阶段 1 至阶段 5 是一次直接契约迁移。施工时允许在阶段内部运行目标测试，但不得为了让旧调用方暂时工作而加入兼容签名。形成可运行检查点后再提交。

建议提交点：

1. `补充Agent运行边界契约测试`
2. `重构Agent持有上下文与运行时`
3. `收敛AgentFactory配置组装`
4. `调整Session按Agent执行`
5. `迁移CLI到完整Agent接口`
6. `清理旧Runtime调用路径`
7. `更新Agent运行架构文档`

每次只暂存本阶段相关文件，不得包含 `.harness-learn/state.db` 或其他用户已有改动。

## 9. 风险与处理

| 风险 | 影响 | 处理方式 |
| --- | --- | --- |
| Agent 与 PromptBuilder 循环导入 | Agent 无法导入 | PromptBuilder 仅在 TYPE_CHECKING 下引用 Agent，运行时不反向导入 |
| Context summarizer 与 Agent LLM 共用实例 | Context 修改 system prompt，污染 Agent 角色提示词 | Session 使用 LLMConfig 创建独立 summarizer LLM |
| GROUP 为每个 Agent 创建 Context | 压缩结果分叉 | 测试对象身份，要求所有 Group Agent 的 context `is` 同一个对象 |
| 跨 Session 误用 Agent 实例 | Context、权限或工具状态串会话 | Session 每次 open 都创建新 Agent；增加同 Agent ID 双 Session 隔离测试 |
| workspace/权限模式更新后仍使用旧环境 | 工具路径或权限错误 | 设置更新后重建全部 Agent，同时保留 Session Context 和 ProcessManager |
| Runtime 接口切换遗漏调用方 | 运行时报参数错误 | 施工前后分别做 CodeGraph impact 检查，最终删除旧签名全文调用 |
| Session 和 Agent 都被误认为负责持久化 | 责任再次混乱 | Agent 只持有 Context 引用；只有 SessionExecution 调用 ContextService |
| 为保持测试通过加入兼容重载 | 长期保留双轨 API | 明确禁止兼容签名，相关阶段按一个契约切换批次完成 |

## 10. 完成定义

只有同时满足以下条件，本计划才可以标记为完成：

1. 生产代码已经形成 `Session -> Agent -> Runtime` 的单向执行入口。
2. Session 创建、恢复和持久化 Context，Agent 持有 Context，Runtime 使用绑定 Context。
3. Agent 是完整可执行对象，不再保存 storage AgentProfile。
4. Session 不再创建或保存裸 Runtime。
5. Runtime 的公开执行方法不再接收 Context。
6. GROUP 只有一份共享 Context，成员 Agent 的 Runtime 彼此隔离。
7. 所有旧接口、兼容路径和过时文档均已清理。
8. 全量测试、编译检查和 diff 检查通过。
