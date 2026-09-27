# LLM 多协议适配开发计划（核心适配已完成）

> 状态：阶段 1 至阶段 6 已完成，计划收口。
>
> 本计划只处理 LLM 请求协议适配，不实现 Skills。Skills 后续只需要使用统一的 `LLM.call_stream()` / `LLM.call()` 接口，不应再依赖某一种厂商协议。

## 1. 目标

当前项目的 `LLM` 只支持 OpenAI Responses API，并且 `Runtime`、`Context` 和测试中存在对 Responses 输出格式的直接依赖。本计划将 LLM 层扩展为多协议入口：

- 保留 OpenAI Responses 的流式和普通请求。
- 增加 OpenAI Chat Completions 的流式和普通请求。
- 增加 Claude Messages 的流式和普通请求。
- 用 `protocol` 字段区分请求协议，不使用含义模糊的 `type`。
- 为每种协议保留明确的专用方法。
- 增加通用 `call_stream()` 和 `call()`，根据 `protocol` 分发。
- 所有协议的响应都转换为当前 Runtime 可以消费的统一内部事件。
- Agent 和 Runtime 只做必要修改，不让协议分支扩散到 Agent Loop。

目标结构：

```text
Runtime
    -> LLM.call_stream(...)
        -> protocol == responses
            -> LLM.call_responses_stream(...)
        -> protocol == completions
            -> LLM.call_completions_stream(...)
        -> protocol == claude
            -> LLM.call_claude_stream(...)
```

普通请求走相同分发链：

```text
Context 压缩 / Agent 辅助请求
    -> LLM.call(...)
        -> call_responses(...)
        -> call_completions(...)
        -> call_claude(...)
```

## 2. 当前实现问题

当前 `code/agent/head/llm.py` 存在以下限制：

1. 构造函数没有协议参数，默认只能调用 OpenAI Responses。
2. `call_responses_stream()` 直接在 LLM 中解析 Responses 专属事件。
3. `call_responses()` 直接返回 OpenAI SDK 的原始 Response 对象。
4. `Runtime.call_llm()` 直接调用 `call_responses_stream()`。
5. `Context.compact_context()` 直接调用 `call_responses()`，因此上下文压缩也绑定 Responses。
6. `LLMConfig` 没有 `protocol` 字段，AgentFactory 无法传递协议配置。
7. `LLMResponseOutputItem` 从 OpenAI `ResponseOutputItem` 导入类型，内部事件类型也偏向 Responses。
8. `Tools.list` 和 `Tools.encode_result()` 的描述和实现部分以 Responses 为目标，后续需要由 LLM 层负责协议转换。
9. `AgentProfileAssistant` 直接使用 `call_responses()`，无法根据 LLM 配置选择协议。

## 3. 设计原则

### 3.1 Adapter 位于 LLM 层

协议适配属于模型调用层，不属于 Runtime：

```text
Runtime = Agent Loop、权限暂停、Tool 调度、Context 追加
LLM = 统一调用入口、协议选择、协议适配
```

Runtime 不允许出现以下逻辑：

```python
if protocol == "responses"
if protocol == "completions"
if protocol == "claude"
```

Runtime 不应直接知道以下厂商细节：

- `responses.stream`
- `chat.completions.create`
- `messages.create`
- `response.output_item.done`
- `content_block_delta`
- Claude 的 `tool_use` / `tool_result`

### 3.2 专用方法和通用方法同时保留

专用方法用于隔离协议实现、单独测试协议和兼容现有调用方。通用方法用于 Runtime 和上层业务统一调用。

### 3.3 请求统一，响应也统一

不能只统一请求函数名。每个专用方法都必须把厂商响应转换为项目内部的 `LLMResponse` 和 `LLMResponseOutputItem`，否则 Runtime 仍然会被协议格式污染。

## 4. 协议命名

### 4.1 `protocol` 字段

不使用 `type` 字段，统一命名为：

```text
protocol
```

字段含义：`protocol` 表示 LLM 请求/响应协议，也是 LLM 层选择请求适配方式的唯一配置字段。

支持值：

| 值 | 含义 | 默认 SDK/接口 |
| --- | --- | --- |
| `responses` | OpenAI Responses 风格协议 | `OpenAI.responses` |
| `completions` | Chat Completions 风格协议 | Chat Completions 接口 |
| `claude` | Claude Messages 风格协议 | Claude Messages 接口 |

服务商名称不进入 LLM 配置模型。实际请求地址由 `base_url` 决定，认证由 `api_key` 决定；只要服务端遵循对应协议，就使用对应的 `protocol`。

### 4.2 协议校验

新增统一校验函数，例如：

```python
SUPPORTED_PROTOCOLS = {"responses", "completions", "claude"}
validate_protocol(protocol)
```

要求：

- `protocol` 必须是非空字符串。
- 只允许已实现协议。
- 不允许通过任意字符串动态导入模块。
- 未知协议在构造时立即失败。
- 新增协议时增加明确的协议名和对应专用方法，不增加服务商字段。

## 5. 内部请求和响应契约

### 5.1 第一版保留当前输入形态

专用方法先接受当前项目的内部输入：

```python
input: str | list[dict[str, Any]]
tools: list[dict[str, Any]] | None
instructions: str | None
```

其中：

- `input` 是 Context 生成的内部消息快照或普通文本。
- `tools` 是项目内部 Tool schema，不能在 Runtime 中按厂商格式构造。
- `instructions` 是当前调用使用的系统指令；为 `None` 时使用 `LLM.system_prompt`。

Context 的详细迁移方案见第 9 节。

### 5.2 `LLMResponse` 统一事件

保留现有 `LLMResponse` 名称，但补齐和规范字段：

```python
@dataclass
class LLMResponse:
    type: str
    text: str | None = None
    data: list[LLMResponseOutputItem] | None = None
    is_stop: bool | None = None
    arguments: dict[str, Any] | None = None
    name: str | None = None
    call_id: str | None = None
    usage: LLMUsage | None = None
    message: Any | None = None
```

字段备注：

| 字段 | 备注 |
| --- | --- |
| `type` | 内部事件类型，不是协议类型；建议值为 `text`、`reasoning`、`reasoning_summary`、`function_call`、`done`、`error` |
| `text` | 流式文本增量或普通文本结果 |
| `data` | 完整响应的内部输出项列表，用于当前 Runtime 写入消息和工具调用 |
| `is_stop` | 本轮没有待处理 Tool Call 且可以结束 Agent Loop 时为 True |
| `arguments` | 兼容字段；工具调用参数统一为已解析字典，不再保存 JSON 字符串 |
| `name` | 工具调用名称 |
| `call_id` | 工具调用稳定 ID，三种协议都必须映射到这里 |
| `usage` | 统一 Token 使用量；缺失时为 None 或约定的零值 |
| `message` | 内部错误或诊断信息；禁止向 Web 暴露密钥和完整请求体 |

### 5.3 `LLMResponseOutputItem`

当前类型依赖 OpenAI `ResponseOutputItem`，第一版可以保留名称，但要把转换逻辑从 Responses 专属类型中隔离：

```python
class LLMResponseOutputItem:
    type: str
    id: str | None
    content: str | list | None
    name: str | None
    arguments: str | dict[str, Any] | None
    call_id: str | None
    status: str | None
```

备注：

- `type` 至少支持 `message`、`function_call`。
- `content` 兼容 OpenAI 和 Claude 归一化后的文本片段。
- `arguments` 内部优先使用字典，为兼容已有 Context 暂时接受 JSON 字符串。
- `call_id` 必须由 Adapter 填充。
- 不要求所有协议转换为 OpenAI SDK 类型。

### 5.4 `LLMUsage`

保留统一字段：

```text
total_tokens
cached_token
output_tokens
input_tokens
```

不同协议缺失字段时统一使用 0，保证 Context 治理的数值计算稳定。新增转换函数：

```text
LLMUsage.from_responses_usage(...)
LLMUsage.from_completions_usage(...)
LLMUsage.from_claude_usage(...)
```

## 6. `LLM` 类详细改造

修改文件：

```text
code/agent/head/llm.py
code/agent/head/types.py
```

### 6.1 构造函数和属性

当前构造函数：

```python
LLM(base_url, api_key, model, system_prompt="")
```

改为显式协议参数，推荐关键字参数：

```python
LLM(
    base_url: str,
    api_key: str,
    model: str,
    protocol: str = "responses",
    system_prompt: str = "",
)
```

属性备注：

| 属性 | 说明 |
| --- | --- |
| `api_key` | 当前请求凭据，只保存在 LLM 内存对象，不写日志、不返回前端 |
| `model` | 当前模型名 |
| `protocol` | 请求协议：`responses`、`completions` 或 `claude` |
| `base_url` | 协议对应的服务地址 |
| `system_prompt` | 默认系统指令；调用时可用 `instructions` 临时覆盖 |
| `client` | OpenAI 客户端，仅供 OpenAI 协议使用 |
| `anthropic_client` | Claude 客户端，仅在 `protocol=claude` 时初始化 |

兼容性要求：

- 默认 `protocol="responses"`，使旧 CLI、测试和直接构造代码暂时可运行。
- 生产代码必须显式从 `LLMConfig.protocol` 传入，默认值仅用于迁移和测试兼容。
- 构造器先校验 `base_url`，不能继续对空字符串执行 `base_url[-3:]`。
- 不同 SDK 的客户端不能互相复用。

### 6.2 通用方法

新增：

```python
def call_stream(
    self,
    input: str | list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    instructions: str | None = None,
) -> Generator[LLMResponse, Any, None]:
    """根据 protocol 发起统一流式请求。"""

def call(
    self,
    input: str | list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    instructions: str | None = None,
) -> Any:
    """根据 protocol 发起统一普通请求。"""
```

分发规则：

```python
if self.protocol == "responses":
    return self.call_responses_stream(input, tools, instructions)
if self.protocol == "completions":
    return self.call_completions_stream(input, tools, instructions)
if self.protocol == "claude":
    return self.call_claude_stream(input, tools, instructions)
raise UnsupportedProtocolError(...)
```

普通 `call()` 使用对应非流式方法。通用方法是 Runtime 和大多数上层调用方的唯一推荐入口。

### 6.3 Responses 专用方法

保留并扩展：

```python
def call_responses_stream(self, input, tools=None, instructions=None) -> Generator[LLMResponse, Any, None]: ...
def call_responses(self, input, tools=None, instructions=None) -> Any: ...
```

要求：

- 临时 `instructions` 优先于 `self.system_prompt`。
- 文本 delta 转成 `LLMResponse(type="text", text=...)`。
- reasoning 事件继续转成 `reasoning` 和 `reasoning_summary`。
- function call 必须提取 `call_id`、`name` 和已解析参数。
- completed 转成统一 `done` 和内部输出项。
- 不把 OpenAI SDK 原始 Response 泄漏给 Runtime。

### 6.4 Completions 专用方法

新增：

```python
def call_completions_stream(self, input, tools=None, instructions=None) -> Generator[LLMResponse, Any, None]: ...
def call_completions(self, input, tools=None, instructions=None) -> Any: ...
```

转换规则：

```text
instructions -> 第一条 system message
input        -> Chat Completions messages
tools        -> {type: function, function: ...} 格式
```

要求：

- 支持字符串输入和 Context 消息列表。
- 明确 system/developer 消息去重和顺序规则。
- 从 `choices[].delta.content` 转换文本事件。
- 聚合跨 chunk 的 `delta.tool_calls`，完整后再发出 function call。
- 保留工具调用 ID、名称和完整参数。
- `finish_reason="tool_calls"` 时 `done.is_stop=False`。
- `finish_reason="stop"` 且无工具调用时 `done.is_stop=True`。
- usage 缺失时按统一约定处理。
- 普通调用返回统一可提取文本的内部结果，不泄漏原始 `ChatCompletion`。

### 6.5 Claude 专用方法

新增：

```python
def call_claude_stream(self, input, tools=None, instructions=None) -> Generator[LLMResponse, Any, None]: ...
def call_claude(self, input, tools=None, instructions=None) -> Any: ...
```

转换规则：

```text
instructions -> Claude Messages 的 system 参数
input        -> Claude messages
tools        -> name/description/input_schema 格式
```

要求：

- 使用 Anthropic 客户端或确定的 Claude HTTP 客户端，不调用 OpenAI client。
- 将内部消息转换为 Claude `role/content`。
- 将 tool call/result 转换为 Claude `tool_use`/`tool_result` 内容块。
- `content_block_delta` 文本转成 text。
- 聚合 `tool_use` 内容块为统一 function call。
- `message_stop` 根据 stop reason 设置 `done.is_stop`。
- 将 input/output token 映射到统一 usage，cached token 缺失时为 0。

### 6.6 Adapter 的实现形态

第一版允许 Adapter 作为 `LLM` 内部方法：

```text
LLM
├── call_responses_stream
├── call_responses
├── call_completions_stream
├── call_completions
├── call_claude_stream
├── call_claude
├── call_stream
└── call
```

当 `llm.py` 变得过长时再拆为：

```text
code/agent/head/adapters/
├── __init__.py
├── responses.py
├── completions.py
└── claude.py
```

拆分后 LLM 仍然持有和调用 Adapter，外部接口不变；不把 Adapter 提升为 Runtime 依赖。

## 7. `LLMConfig` 和 Storage 改造

### 7.1 `code/agent/head/types.py`（修改）

`LLMConfig` 新增：

```python
protocol: str = "responses"
```

建议：

```python
@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    protocol: str = "responses"
```

属性备注：`base_url` 是服务地址；`api_key` 是数据库读取的密钥；`model` 是模型标识；`protocol` 是协议。

新增代码必须使用关键字构造 `LLMConfig`，避免字段扩展导致位置参数错位。

### 7.2 `code/agent/storage/types.py`（修改）

`LLMProfile` 新增：

```python
protocol: str = "responses"
```

该字段持久化用户选择的请求协议，恢复 Session 时原样传递给 `LLMConfig`。它不是 Agent 属性，也不由 Runtime 推断。

### 7.3 `code/agent/storage/migrations.py`（修改）

当前 schema 为 5。新增显式版本迁移，例如：

```text
CURRENT_SCHEMA_VERSION = 6
_migrate_version_five_to_six()
```

迁移内容：

```sql
ALTER TABLE llm_profiles
ADD COLUMN protocol TEXT NOT NULL DEFAULT 'responses';
```

旧配置全部默认为 `responses`，不自动推断 Claude。新数据库初始 schema 也必须包含该字段。

本次迁移同时删除旧的 `provider` 列：

```sql
ALTER TABLE llm_profiles DROP COLUMN provider;
```

如果目标 SQLite 版本或现有表结构不支持直接 `DROP COLUMN`，必须采用“创建新表、复制保留字段、替换旧表”的显式迁移方式，不能只在代码中忽略 `provider`。迁移完成后，数据库 schema、领域对象、Repository、API DTO 和前端类型都不得继续保留该字段。

### 7.4 `code/agent/storage/repositories/llm_profile.py`（修改）

修改插入、更新、读取和转换逻辑：

- `INSERT` 增加 `protocol`，并移除 `provider`。
- `ON CONFLICT` 更新 `protocol`，不再读写 `provider`。
- `_from_row()` 读取 `protocol`。
- 值非法时转换为稳定 `StorageFormatError`。

Repository 不创建客户端，不发送请求，只负责 LLMProfile 持久化。

## 8. Agent 修改范围

Agent 改动很小，主要是接收完整 `LLMConfig`。

### 8.1 `code/agent/runtime/agent.py`（修改）

把当前位置参数调用改为：

```python
LLM(
    base_url=llm_config.base_url,
    api_key=llm_config.api_key,
    model=llm_config.model,
    protocol=llm_config.protocol,
    system_prompt=instructions,
)
```

必须保留：Agent 持有 LLM、Agent 创建 Runtime、Agent 不判断 protocol、Agent 不调用协议专用方法。

### 8.2 `code/agent/runtime/agent_factory.py`（修改）

`_to_llm_config()` 增加：

```python
protocol=profile.protocol,
```

Factory 不选择 Adapter，不拼协议请求体，只把持久化配置转换成 `LLMConfig`。

### 8.3 `code/agent/session/session_service.py`（修改）

创建 Context summarizer 的 LLM 时传递 `protocol`，并确保 Context 压缩使用通用 `call()`。

Session 不负责协议分发，只负责传递配置。

### 8.4 `client/web/server/app/services/agent_profile_assistant.py`（修改）

当前服务直接调用 `call_responses()`，需要：

- `LLMFactory` 增加 protocol 参数，不再接收 provider。
- 使用关键字构造 LLM。
- 改用 `llm.call()`。
- 通过统一文本提取接口解析响应，不再假设只有 `output_text` 属性。

## 9. Context 和 Runtime 修改范围

Context 是本次多协议适配中需要单独治理的部分。原因是当前 Context 虽然属于 Session 层的上下文对象，但内部消息快照仍然带有 Responses 协议字段。若只把 Runtime 的调用改成 `call_stream()`，Completions 和 Claude 仍然无法可靠恢复历史 Tool Call/Tool Result。

### 9.1 Context 的目标职责

Context 继续由 Session 创建和持有，负责一个 Session 的当前模型上下文及其治理：

- 保存用户消息、Agent 消息、Tool Call、Tool Result 和必要的系统事实。
- 提供安全的追加、导出、恢复和深拷贝隔离。
- 根据统一的 `LLMUsage` 触发工具调用精简和上下文压缩。
- 只依赖项目内部的消息格式和通用 `LLM.call()`。
- 不知道 Responses、Completions、Claude 的请求字段和角色规则。

Context 不负责：

- 组装厂商请求体。
- 选择 `protocol`。
- 生成 OpenAI `function_call_output`、Chat Completions `tool` 消息或 Claude `tool_result`。
- 扫描 Skill、执行 Bash 或判断权限。
- 把 Skill 正文追加为历史消息。

### 9.2 内部消息模型

当前 Context 使用 Responses 风格的 `type` 消息。新写入的 Context 应逐步改为项目内部的稳定格式：

```python
{
    "kind": "message",
    "role": "user",
    "content": "请读取 README"
}
```

```python
{
    "kind": "message",
    "role": "assistant",
    "content": "我先检查文件。"
}
```

```python
{
    "kind": "tool_call",
    "tool_call_id": "call_001",
    "tool_name": "read",
    "arguments": {"path": "README.md"}
}
```

```python
{
    "kind": "tool_result",
    "tool_call_id": "call_001",
    "output": {"status": "ok", "data": "..."}
}
```

字段备注：

| 字段 | 备注 |
| --- | --- |
| `kind` | 项目内部消息种类；至少支持 `message`、`tool_call`、`tool_result`、`system_event` |
| `role` | 仅 `message` 使用，表示 `user`、`assistant` 或内部事实消息 |
| `content` | 普通消息文本或标准化内容块 |
| `tool_call_id` | Tool 调用和结果之间的稳定关联 ID |
| `tool_name` | Tool 名称，不是协议字段，由 Adapter 转换为各协议的工具名称字段 |
| `arguments` | 已解析的 JSON 对象，禁止新代码保存 JSON 字符串 |
| `output` | ToolResult 的结构化输出或受限制的文本结果 |

内部格式的目标是让 Context 保存“发生了什么”，而不是保存“某个厂商要求如何表达这件事”。

### 9.3 `code/agent/context/context.py` 修改内容

必须修改：

1. `append_function_call()` 新写入 `kind="tool_call"`、`tool_call_id`、`tool_name` 和字典 `arguments`。
2. `append_function_call_output()` 新写入 `kind="tool_result"`、`tool_call_id` 和 `output`。
3. `_normalize_message()` 支持内部消息对象和旧 Responses 消息，不允许未知结构静默进入 Context。
4. `restore()` 先通过快照 Codec 归一化旧格式，再写入内存内部格式。
5. `export()` 只返回内部格式的深拷贝。
6. `to_model_input()` 不再拼接厂商格式的 `system_messages`；第一阶段可以保留兼容入口，但应标记为过渡接口并让 Runtime 改用 `export()`。
7. `compact_context()` 改用 `self.llm.call()`，不再调用 `call_responses()`。
8. 压缩结果写回内部 `kind="message"` 的事实摘要，而不是 Responses 的 `role="developer"` 和 `input_text` 组合。
9. `function_call_manager()` 按 `kind="tool_call"` 精简旧调用，保留最近 `call_result_num` 次；替换结果仍是内部事实消息。
10. `set_usage()` 和 `check_point()` 继续负责治理，不改变阈值语义。

建议提供的接口：

```python
append_user_message(text: str) -> InternalMessage
append_agent_message(agent_id: str, text: str) -> InternalMessage
append_tool_call(agent_id: str, call: ToolCall) -> InternalMessage
append_tool_result(agent_id: str, result: ToolResult) -> InternalMessage
restore(messages: list[dict[str, Any]]) -> None
export() -> list[dict[str, Any]]
compact_context() -> list[dict[str, Any]]
```

现有 `append_function_call()` 和 `append_function_call_output()` 可以先保留为兼容别名，但新代码和 Runtime 应切换到语义更清晰的 `append_tool_call()` / `append_tool_result()`。兼容别名必须在所有调用方迁移后删除，不能永久保留两套写入格式。

### 9.4 上下文压缩

压缩流程保持现有治理思想，但协议调用改为通用入口：

```text
Context 当前内部消息
    -> 计算保留尾部和待压缩前缀
    -> LLM.call(input=压缩请求, instructions=压缩指令)
    -> 统一文本提取
    -> 校验摘要
    -> 用内部摘要消息替换旧前缀
    -> export 当前内部上下文
```

压缩要求：

- 压缩模型使用当前 `LLM` 的 `protocol`，但 Context 不知道具体协议。
- 压缩输入可以是 JSON 文本，但只作为压缩请求的普通输入，不写入正式 Context。
- 压缩调用失败时不修改当前上下文。
- 摘要必须是字符串或经过明确校验的结构化摘要，不能把厂商 Response 对象放入 Context。
- 摘要消息要明确标记为历史事实，不能伪装成新的用户消息。
- 压缩后的消息仍然使用内部格式，恢复时无需再次转换为 Responses。
- Skill 的 instructions 不进入压缩范围；Skill 配置通过 Agent/LLM instructions 重新组装。

建议新增内部接口：

```python
summary = self.llm.extract_text(self.llm.call(
    input=compaction_input,
    instructions=COMPACTION_INSTRUCTIONS,
))
```

### 9.5 Context 快照 Codec

新增文件：

```text
code/agent/context/message_types.py
code/agent/context/snapshot_codec.py
tests/context/test_snapshot_codec.py
```

职责：

- `message_types.py` 定义内部消息、Tool Call、Tool Result 的类型和字段校验。
- `snapshot_codec.py` 负责旧快照识别、旧格式归一化和新格式编码。

建议接口：

```python
decode_snapshot(raw: list[dict[str, Any]]) -> list[dict[str, Any]]
encode_snapshot(messages: list[dict[str, Any]]) -> list[dict[str, Any]]
normalize_legacy_message(message: dict[str, Any]) -> dict[str, Any]
```

兼容规则：

| 旧格式 | 内部格式 |
| --- | --- |
| `type=message` + `role=user/assistant` | `kind=message` |
| `type=function_call` + `call_id/name/arguments` | `kind=tool_call` |
| `type=function_call_output` + `call_id/output` | `kind=tool_result` |
| `type=message` + `role=developer` 的历史摘要 | `kind=message` + `role=system_event` |
| 未知 `type` | 返回稳定格式错误，不静默丢弃 |

旧快照的迁移策略：

1. 读取 `sessions.current_context_json` 时先 decode。
2. 内存中只保留内部格式。
3. 本轮执行或恢复后保存时统一 encode 新格式。
4. 不修改历史 `context_items` 的业务语义。
5. 如果旧快照损坏，优先回退到可恢复的业务事件时间线，并记录诊断信息；不能让单个会话阻塞整个应用启动。

### 9.6 `code/agent/storage/context_service.py` 修改内容

当前 `ContextService.to_responses_input()` 直接生成 Responses 消息，必须拆分职责：

- 保留业务事件读取和写入。
- 将 `to_responses_input()` 改为 `to_internal_messages()`，生成内部消息格式。
- `restore_context()` 把内部消息交给 `Context.restore()`。
- `save_context()` 保存 `Context.export()` 的内部快照。
- 不在 ContextService 中生成 Responses、Completions 或 Claude 专属字段。

建议迁移接口：

```python
to_internal_messages(items: list[ContextItem]) -> list[dict[str, Any]]
```

业务事件映射：

```text
USER_MESSAGE          -> kind=message, role=user
AGENT_MESSAGE         -> kind=message, role=assistant
FUNCTION_CALL         -> kind=tool_call
FUNCTION_CALL_OUTPUT  -> kind=tool_result
SYSTEM_EVENT          -> kind=system_event
AGENT_DELEGATION      -> kind=system_event 或专用内部事件
```

函数名 `to_responses_input` 的兼容别名只保留到所有调用方迁移完成，之后删除，避免后续继续把 Context 理解为 Responses 专属对象。

### 9.7 LLM Adapter 的 Context 投影

Context 内部格式转换为厂商格式必须由 LLM 专用方法或其 Adapter 完成：

```text
Context.internal_messages
    -> Responses: input message/function_call/function_call_output
    -> Completions: user/assistant/tool messages
    -> Claude: user/assistant + tool_use/tool_result content blocks
```

映射要求：

- Responses 的 Tool Call 使用 `call_id`、`name`、JSON arguments。
- Completions 的 Tool Call 使用 assistant `tool_calls` 和 `tool_call_id`。
- Claude 的 Tool Call 使用 assistant `tool_use`，结果使用 user `tool_result`。
- 不修改 Context 内部消息来适配某个协议。
- 厂商不支持的内部事件必须转换为事实文本或明确报错，不能静默丢弃。

### 9.8 Runtime 的 Context 调用修改

#### `code/agent/runtime/runtime.py`（修改一处）

当前：

```python
return self.llm.call_responses_stream(
    self.context.to_model_input(self.sys_message),
    self.tools.list,
)
```

改为：

```python
return self.llm.call_stream(
    input=self.context.export(),
    tools=self.tools.list,
    instructions=self.sys_message,
)
```

`sys_message` 需要在后续实现中从 Responses message 列表改为普通的内部 instructions 文本，或者由 PromptBuilder 统一生成。Runtime 不增加协议判断，不增加协议专用方法。

#### `code/agent/context/context.py`

当前压缩调用：

```python
response = self.llm.call_responses([...])
```

改为：

```python
response = self.llm.call([...])
```

同时增加统一文本提取接口，例如 `extract_text(response) -> str`。Context 不判断 Responses、Completions、Claude，也不负责拼接 system message。

#### `code/agent/storage/context_service.py`

恢复和保存统一使用内部消息快照；`to_responses_input()` 迁移为 `to_internal_messages()`，并在所有调用方迁移完成后删除旧兼容名称。

#### 9.9 Context 迁移顺序

为避免一次修改同时破坏 Runtime、Session 持久化和已有数据库，按以下顺序实施：

1. 先增加内部消息类型和 Snapshot Codec，补充旧 Responses 快照读取测试。
2. 让 `Context.restore()` 能读取旧格式并统一转换到内存内部格式。
3. 让 `Context.export()` 输出内部格式，并让 `ContextService.save_context()` 保存新格式。
4. 将 `ContextService.to_responses_input()` 改成 `to_internal_messages()`，恢复新 Session 时生成内部消息。
5. 修改 Runtime 使用 `context.export()`，把系统环境作为 instructions 传给 `LLM.call_stream()`。
6. 修改 Context 压缩使用 `LLM.call()` 和统一文本提取。
7. 将 LLM Adapter 的协议投影测试接入 Responses、Completions、Claude。
8. 确认所有生产调用方不再依赖 `to_model_input()`、`to_responses_input()` 和 `call_responses*` 后，删除兼容别名。

每一步都必须保证已有 Session 可以打开；不能先删除旧格式再实现恢复转换。

### 9.3 `runtime_events.py`（可能修改）

如果仍使用 `LLMResponse`，无需实质改动；只有响应类型重命名时才调整导入，不增加协议字段。

## 10. Tools 修改范围

`code/agent/tools/tools.py` 只做注释和契约澄清：`Tools.list` 是项目内部 Tool schema，不属于任何协议；`encode_result()` 产生内部结果，具体协议包装由 LLM 层完成。

各协议在 LLM 层实现纯转换函数：

```text
_to_responses_tools(tools)
_to_completions_tools(tools)
_to_claude_tools(tools)
```

映射：

```text
内部 Tool
    -> Responses: {type: function, name, description, parameters}
    -> Completions: {type: function, function: {...}}
    -> Claude: {name, description, input_schema}
```

## 11. Web 配置和 API 修改范围

需要把 `protocol` 贯穿配置链路，否则用户无法选择协议。

### 11.1 Backend

修改：

```text
client/web/server/app/schemas/settings.py
client/web/server/app/api/settings.py
client/web/server/app/services/llm_model_discovery.py
```

`LLMProfileSummary`、创建 DTO、更新 DTO 和模型发现请求增加：

```python
protocol: Literal["responses", "completions", "claude"]
```

Claude 不能误用 OpenAI `/models` 发现流程；暂不支持的发现方式必须返回明确错误。

### 11.2 Frontend

修改：

```text
client/web/front/src/api/types.ts
client/web/front/src/features/settings/api.ts
client/web/front/src/features/settings/components/CreateLlmDialog.tsx
client/web/front/src/features/settings/pages/LLMSettingsPage.tsx
```

新增：

```typescript
export type LLMProtocol = "responses" | "completions" | "claude";
```

UI 新增“请求协议”下拉框，编辑时回显，列表显示 protocol 和 model；删除 provider 的展示和提交字段。

## 12. 测试计划

### 12.1 类型和构造

- `LLMConfig` 默认 `protocol="responses"`。
- 三种协议可以显式构造。
- 未知协议在构造阶段失败。
- 生产代码使用关键字参数。

### 12.2 Responses

- 请求使用 instructions、input 和转换后的 tools。
- 文本、reasoning、function call、completed、usage 正确归一化。
- function call 包含 call ID、名称和参数。
- 普通调用返回统一可提取文本的结果。

### 12.3 Completions

- system prompt 转为第一条 system message。
- 流式文本 chunk 正确归一化。
- 分片 Tool Call 参数正确聚合。
- Tool Result 使用 `role="tool"` 和正确 `tool_call_id`。
- stop reason 和 usage 映射正确。

### 12.4 Claude

- system prompt 使用 system 参数。
- Tool schema 转换为 input_schema。
- tool_use 转换为统一 function call。
- tool_result 使用 Claude 内容块。
- 文本 delta、message stop、usage 正确转换。

### 12.5 Runtime 和 Context

- Runtime 只调用 `call_stream()`。
- Context 压缩只调用 `call()`。
- 新写入 Context 使用内部 `kind` 消息格式。
- 旧 Responses 快照可以被 Codec 恢复并转换为内部格式。
- Context 导出和持久化不包含 `function_call`、`function_call_output` 等厂商协议字段。
- `ContextService` 不再生成 Responses 专属输入。
- Context 压缩失败时保留压缩前消息，成功时写回内部摘要消息。
- 不同协议下权限暂停、Tool 执行、恢复和 Context 压缩一致。
- 现有 Responses 测试全部通过。

### 12.6 Web/API

- LLM Profile 创建、编辑、读取正确保存 protocol。
- 旧数据库迁移后 protocol 为 responses。
- 非法组合返回稳定 422。
- Claude 不调用 OpenAI `/models`。
- API 不泄露 API Key。

## 13. 分阶段施工

### 阶段 0：内部契约和兼容策略

**修改**：`code/agent/head/types.py`。

**内容**：固定 protocol 值和校验规则；补齐统一响应事件；准备三种协议的测试夹具。

**验收**：内部事件可以表达文本、Tool Call、完成和错误。

### 阶段 1：重构 Responses 到通用入口

**修改**：`code/agent/head/llm.py`。

**内容**：增加 protocol；保留 Responses 专用方法；新增 `call_stream` 和 `call`；支持临时 instructions。

**验收**：旧 Responses 行为不变，Runtime 可以使用通用入口。

### 阶段 2：Completions 适配

**新增/修改**：`code/agent/head/llm.py` 或 `code/agent/head/adapters/completions.py`。

**内容**：实现流式/普通请求、消息、工具、工具结果和流事件转换。

### 阶段 3：Claude 适配

**新增/修改**：`code/agent/head/llm.py` 或 `code/agent/head/adapters/claude.py`。

**内容**：初始化客户端，实现流式/普通请求和 Claude 内容块转换。

### 阶段 4：Context 内部格式和快照兼容

**新增**：

- `code/agent/context/message_types.py`
- `code/agent/context/snapshot_codec.py`
- `tests/context/test_snapshot_codec.py`

**修改**：

- `code/agent/context/context.py`
- `code/agent/storage/context_service.py`
- `code/agent/storage/context_service.py` 的恢复/保存调用链。

**内容**：

- 定义内部 `message`、`tool_call`、`tool_result`、`system_event` 格式。
- 旧 Responses 快照读取时转换为内部格式。
- 新快照统一保存内部格式。
- `Context` 的追加、导出、恢复和精简只面向内部格式。
- Context 压缩调用通用 `LLM.call()`，不保存压缩请求本身。

**验收**：旧 Session 快照可以恢复，新快照不含 Responses 专属字段，压缩失败不改变原上下文。

### 阶段 5A：Agent、Context、Runtime 接入（已完成）

**修改很少，但必须完成**：

- `agent.py`：传入 protocol，使用关键字参数。
- `agent_factory.py`：Profile 映射到 LLMConfig。
- `runtime.py`：使用 `context.export()`，调用 `call_stream()` 并单独传递 instructions。
- `context.py`：调用 `call()`、统一文本提取和内部摘要消息。
- `session_service.py`：创建 summarizer 时传入 protocol。
- `runtime_events.py`：仅在统一类型改变时调整导入。

**验收**：Runtime 不拼接厂商消息；Context 不调用协议专用方法；系统环境和 Agent 指令不写入 Context 历史。

**明确不做**：Runtime 不加协议分支；Agent 不加专用调用方法；Adapter 不注入 Runtime；不改变 Session 组装职责。

### 阶段 5B：Storage、API、UI 配置 protocol（已完成）

**修改**：

```text
code/agent/storage/types.py
code/agent/storage/migrations.py
code/agent/storage/repositories/llm_profile.py
client/web/server/app/schemas/settings.py
client/web/server/app/api/settings.py
client/web/server/app/services/llm_model_discovery.py
client/web/front/src/api/types.ts
client/web/front/src/features/settings/api.ts
client/web/front/src/features/settings/components/CreateLlmDialog.tsx
client/web/front/src/features/settings/pages/LLMSettingsPage.tsx
```

**验收**：用户可以创建、编辑和恢复带不同 protocol 的 LLM 配置。

### 阶段 6：辅助调用方迁移和兼容收口（本次完成）

**修改**：`agent_profile_assistant.py`、`code/cli/main.py`、所有 Fake LLM 和相关测试。

**内容**：生产代码使用通用入口；旧专用方法只保留在 LLM 实现和协议测试中；删除不再需要的兼容分支。

**实际完成**：Session summarizer、AgentProfileAssistant、Runtime、Context 和
Session 持久化链路已使用通用入口或协议无关消息格式；旧 Responses 快照仍可恢复。
阶段 5B 已完成：protocol 已贯通 Storage、API、UI，并完成旧 schema 迁移。

## 14. 文件清单

### 必须修改

```text
code/agent/head/types.py
code/agent/head/llm.py
code/agent/runtime/agent.py
code/agent/runtime/agent_factory.py
code/agent/runtime/runtime.py
code/agent/context/context.py
code/agent/context/message_types.py
code/agent/context/snapshot_codec.py
code/agent/storage/context_service.py
code/agent/session/session_service.py
code/agent/storage/types.py
code/agent/storage/migrations.py
code/agent/storage/repositories/llm_profile.py
client/web/server/app/schemas/settings.py
client/web/server/app/api/settings.py
client/web/server/app/services/agent_profile_assistant.py
client/web/front/src/api/types.ts
client/web/front/src/features/settings/api.ts
client/web/front/src/features/settings/components/CreateLlmDialog.tsx
client/web/front/src/features/settings/pages/LLMSettingsPage.tsx
```

### 可能新增

```text
code/agent/head/adapters/__init__.py
code/agent/head/adapters/responses.py
code/agent/head/adapters/completions.py
code/agent/head/adapters/claude.py
tests/head/test_llm_responses.py
tests/head/test_llm_completions.py
tests/head/test_llm_claude.py
```

如果专用方法仍能保持清晰且 `llm.py` 没有失控，不强制拆 Adapter 文件；外部接口和职责必须保持本文定义。

### 不应修改职责的文件

```text
code/agent/permission/*
code/agent/tools/bash.py
code/agent/tools/shell/*
code/agent/session/ExecutionContext.py
```

除非测试暴露明确兼容问题，否则不改权限、Bash、进程和 Session 环境模型。

## 15. 完成定义

LLM 多协议适配及 Storage/API/UI 配置已经完成，计划可以收口：

- `LLM` 有 `protocol` 属性，支持 Responses、Completions、Claude 三种协议。
- 每种协议都有流式和普通专用方法。
- `call_stream()` 和 `call()` 能根据 protocol 正确分发。
- 三种协议都返回统一的内部事件和工具调用结构。
- Runtime 不包含协议分支，只调用通用方法。
- Context 压缩不再固定调用 Responses。
- AgentFactory 正确传递 protocol。
- LLM Profile、数据库迁移、API 和 UI 支持 protocol。
- 旧配置默认保持 Responses 行为。
- Tool Call、Tool Result、权限暂停、恢复和上下文压缩在三种协议下都有测试。
- API Key、完整请求体和厂商错误细节不会进入日志或 Web 响应。
- `call_responses*` 兼容入口去留已经明确，且不存在未说明的兼容分支。
