# Read 与 Write 工具优化迭代计划

## 1. 计划状态

- 当前状态：已完成。阶段 0-6 全部完成，全量测试通过。
- 适用范围：`read` 与 `write` 两个基础文件工具，以及它们依赖的参数准备、执行上下文和工具结果契约。
- 不包含：`edit`、`bash` 的行为重构，权限模式重构，操作系统级沙箱，以及新增 Web UI。

## 2. 背景与问题

当前 `read` 已能读取 UTF-8 文本、目录和图片，`write` 已能创建或覆盖文本文件，并且两个工具都接入了统一的路径解析、Session 权限判断和 `ToolResult` 结果协议。这些能力足够支持基本 Agent Loop，但边界行为仍不完整。

已确认的问题包括：

1. `read(limit=-1)` 会绕过 `ExecutionContext.max_tool_call_length`，因为 Python 的 `read(-1)` 表示读取全文。
2. `read` 对文本流直接执行 `seek(offset)`，现有 `offset` 的字符语义不稳定，尤其容易在多字节文本中产生歧义。
3. 只按行读取无法约束 `*.min.js`、压缩 JSON 等超长单行文件；只按字符读取又不利于普通源代码定位。
4. 目录读取会一次返回全部条目，图片会一次读取全部字节，二者都没有本地硬限制。
5. 图片只按扩展名识别，没有验证文件内容与图片类型是否一致。
6. `write` 通过路径末尾 `/` 推断目录，但 `handle_path()` 规范化后会移除末尾分隔符，因此所谓“创建目录”实际可能创建空文件。
7. `write` 直接用 `w` 覆盖目标，写入失败或进程中断时可能留下被截断的文件。
8. `read/write` 的 JSON Schema 主要用于提示模型，当前 `Tools.prepare_call()` 没有执行完整的本地参数校验。
9. `write` 没有内容大小上限，也没有检测“读取后文件被其他进程修改”的能力。

本计划中的“硬限制”全部由本项目自己的 Tool 执行层实现。第三方 LLM 服务端只负责产生工具参数，不参与、也不能覆盖本地读取和写入限制。

## 3. 目标

### 3.1 Read 目标

1. 普通源码按行读取，返回清晰的行号范围。
2. 超长单行文件在达到本地字符上限时立即停止，并能通过 cursor 从同一行继续读取。
3. 所有文本结果都受 `ExecutionContext.max_tool_call_length` 本地硬上限约束；模型传入任何参数都不能突破。
4. 目录结果同时受条目数量和序列化字符数量限制，并支持继续读取。
5. 图片在读入内存前检查文件大小，并验证支持的图片格式。
6. 参数错误、文件变化、编码不支持和资源过大均返回稳定错误码，不泄漏为笼统内部异常。

### 3.2 Write 目标

1. `write` 只负责创建或完整替换文本文件，不再通过路径格式猜测“文件还是目录”。
2. 自动创建目标文件的父目录，但本阶段不提供创建空目录的能力。
3. 使用同目录临时文件和 `os.replace()` 完成原子替换，避免先截断原文件。
4. 写入内容受本地字节上限约束。
5. 支持可选的文件版本前置条件，发现文件已变化时拒绝覆盖。
6. 返回实际 UTF-8 字节数、创建/替换类型和新文件版本，而不是只返回 Python 字符数。

### 3.3 共同目标

1. LLM 输出始终视为不可信输入；参数在权限检查前完成解析、类型校验和规范化。
2. 权限判断和实际执行继续共享同一个规范化绝对路径。
3. 不引入两套长期并存的 Tool 参数协议；迁移完成后只保留一个权威版本。
4. 每项缺陷先用失败测试复现，再实现修复。

## 4. 非目标

1. 不依赖第三方 LLM 服务端限制响应大小。
2. 不把路径检查包装成操作系统沙箱；现有 Session 权限模型和硬安全策略仍负责是否允许访问。
3. 不让 `read` 成为任意二进制文件下载工具；首期只支持文本、目录和已允许的图片类型。
4. 不在 `write` 内加入追加、局部替换或补丁能力；局部修改仍属于 `edit`。
5. 不在本计划中新增 `mkdir` Tool。`write` 仍会自动创建父目录，但不能单独创建空目录。
6. 不兼容历史 `offset/limit` 文本分页语义。Tool Schema 每轮都会重新提供给模型，历史已完成调用不会重新执行，因此直接迁移到新契约，避免长期兼容分支。

## 5. 架构原则

### 5.1 本地限制链路

```text
第三方 LLM 生成参数
        ↓
Tools.prepare_call 解析并校验参数
        ↓
构造规范化路径和 PermissionRequest
        ↓
PermissionManager 决定 allow / ask / deny
        ↓
Tools.execute 执行前复核目标路径
        ↓
read/write 在本地执行硬上限和文件操作
        ↓
受限 ToolResult 进入 Context 并发送给第三方 LLM
```

`max_tool_call_length` 的权威执行点是本地 `read`，不是 Prompt、JSON Schema 或第三方模型。Schema 中的最大值用于减少错误调用，本地代码中的检查才是安全边界。

### 5.2 参数校验边界

为 `Tool` 增加可选的参数解析器，例如 `prepare_arguments`。`Tools.prepare_call()` 在构造权限请求前调用它，并使用解析器返回的新字典作为 `PreparedToolCall.arguments`。

这样可以保证：

- 权限判断和执行使用完全相同的、已校验参数。
- `read/write` 不需要重复解析模型输入。
- `edit/bash` 暂时可以不配置解析器，后续再独立迁移。
- 参数解析失败统一转换为 `INVALID_ARGUMENTS`，不会进入权限弹窗或工具执行。

不得只更新 JSON Schema 而不做本地校验。

### 5.3 Cursor 原则

Cursor 由 `read` 生成并由 `read` 解析，调用方不得依赖其内部格式。首期使用无服务端状态的版本化 token，至少包含：

- cursor 版本；
- 读取类型：`text` 或 `directory`；
- 下一次读取位置；
- 文件或目录版本信息；
- 文本当前行号及是否处于一行中间。

Cursor 不是权限凭据。每次续读仍必须按 `target_path` 重新执行路径解析和权限判断。Cursor 解析后还必须确认类型、范围和目标资源版本；伪造 cursor 最多导致 `INVALID_CURSOR`，不能扩大访问范围。

## 6. 最终 Tool 契约

### 6.1 Read 输入

```json
{
  "target_path": "src/main.py",
  "cursor": null,
  "start_line": 1,
  "limit": 200
}
```

字段语义：

| 字段 | 必填 | 语义 |
| --- | --- | --- |
| `target_path` | 是 | 相对 workspace 或绝对路径；必须是非空字符串。 |
| `cursor` | 否 | 上一次 `read` 返回的续读位置。传入后不能同时传 `start_line`。 |
| `start_line` | 否 | 文本首次读取的起始行，从 1 开始；默认 1。目录和图片不使用。 |
| `limit` | 否 | 文本最多返回的行片段数，目录最多返回的条目数；必须是正整数。默认 200，并受本地最大值限制。 |

布尔值虽然在 Python 中属于 `int` 子类，但必须明确拒绝；浮点数、零、负数和超出本地最大值的值均不能原样进入执行层。对于超过本地最大值的正整数，统一截断到本地最大值，结果中返回实际使用的 `effective_limit`。

### 6.2 Read 文本结果

```json
{
  "type": "text",
  "path": "/workspace/src/main.py",
  "content": "...",
  "start_line": 1,
  "end_line": 120,
  "returned_line_segments": 120,
  "effective_limit": 200,
  "truncated": true,
  "truncation_reason": "max_chars",
  "continues_line": false,
  "next_cursor": "...",
  "version": "..."
}
```

读取停止条件：

1. 达到 `limit`；或
2. `content` 达到本地 `ctx.max_tool_call_length`；或
3. 到达文件末尾。

任一条件先满足就停止。对于单行大于字符上限的文件，允许在该行中间停止：

- `truncated = true`；
- `truncation_reason = "max_chars"`；
- `continues_line = true`；
- `next_cursor` 指向同一行尚未返回的位置。

下一次带 cursor 调用时从该字符边界继续，不重复或跳过文本，也不能截断 UTF-8 字符。

`version` 使用不透明文件版本 token，至少由规范化路径对应文件的设备/文件标识、字节大小和纳秒修改时间生成。续读前后均检查版本；读取期间或两次读取之间文件发生变化时返回 `FILE_CHANGED`，避免把两个版本的内容拼接为一份结果。

### 6.3 Read 目录结果

```json
{
  "type": "directory",
  "path": "/workspace/src",
  "entries": [
    {"type": "file", "name": "main.py", "path": "/workspace/src/main.py"}
  ],
  "returned": 1,
  "effective_limit": 200,
  "truncated": true,
  "truncation_reason": "max_entries",
  "next_cursor": "...",
  "version": "..."
}
```

目录规则：

- 条目按 `name.casefold()`、原始名称稳定排序。
- 条目类型至少区分 `file`、`directory`、`symlink` 和 `other`。
- 返回数量受 `limit` 和本地 `max_directory_entries` 限制。
- 序列化后的条目数据同时受 `max_tool_call_length` 字符限制。
- 目录版本变化后旧 cursor 返回 `FILE_CHANGED`。
- 符号链接只作为条目展示；后续读取该路径时仍重新解析真实路径并重新走权限判断。

### 6.4 Read 图片结果

保持当前 `ToolResult + Attachment` 结构，但执行以下约束：

- `os.stat()` 先检查大小，超过 `ctx.max_image_bytes` 返回 `FILE_TOO_LARGE`，不得先读入内存。
- 只允许首期支持的 PNG、JPEG、GIF、WebP、BMP。
- 扩展名、MIME 推断和文件签名字节必须一致；不一致返回 `UNSUPPORTED_IMAGE_FORMAT`。
- 图片成功结果返回 `size_bytes` 和 `version`。
- 图片不使用 cursor、`start_line` 或 `limit`；若调用方传入不适用参数，返回 `INVALID_ARGUMENTS`，不静默忽略。

### 6.5 Write 输入

```json
{
  "target_path": "src/generated.py",
  "content": "...",
  "expected_version": "..."
}
```

字段语义：

| 字段 | 必填 | 语义 |
| --- | --- | --- |
| `target_path` | 是 | 目标文件路径，必须是非空字符串。 |
| `content` | 是 | 完整 UTF-8 文本；允许空字符串。 |
| `expected_version` | 否 | 调用方先前从 `read` 获得的文件版本；不匹配时拒绝覆盖。 |

`target_path` 指向现有目录时返回 `TARGET_IS_DIRECTORY`。路径末尾分隔符不再具有“创建目录”的特殊语义。目标父目录不存在时继续自动创建。

### 6.6 Write 结果

```json
{
  "operation": "created",
  "path": "/workspace/src/generated.py",
  "bytes_written": 128,
  "version": "..."
}
```

规则：

- `operation` 只能是 `created` 或 `replaced`。
- `bytes_written` 是 UTF-8 编码后的字节数，不是 Python 字符数。
- `version` 是写入完成后重新读取文件元数据生成的版本 token。
- `expected_version` 不匹配、目标消失或目标由不存在变为存在时返回 `FILE_CHANGED`。
- 不提供 `expected_version` 时保留显式覆盖能力，但仍执行原子替换；结果可增加 `precondition_checked: false`，让调用方知道本次没有并发保护。

## 7. 本地默认限制

在 `ExecutionContext` 中保留现有 `max_tool_call_length = 20_000`，并增加用途明确的本地限制：

| 配置 | 建议默认值 | 用途 |
| --- | --- | --- |
| `max_tool_call_length` | 20,000 字符 | 单次文本内容或目录条目序列化内容上限。 |
| `max_read_lines` | 1,000 | 单次文本最多返回的行片段数。 |
| `max_directory_entries` | 500 | 单次目录最多返回的条目数。 |
| `max_image_bytes` | 10 MiB | 单张图片允许读入内存的最大字节数。 |
| `max_write_bytes` | 2 MiB | 单次文本文件允许写入的最大 UTF-8 字节数。 |

这些值是本地运行时配置，不发送给第三方 LLM 作为可信约束。JSON Schema 可以公开合理的调用范围，但执行层必须再次使用 `ExecutionContext` 中的值裁剪或拒绝。

## 8. 稳定错误码

在现有 `ToolResult.failure()` 协议内统一使用以下错误码：

| 错误码 | 场景 | retryable |
| --- | --- | --- |
| `INVALID_ARGUMENTS` | 类型错误、范围错误、互斥参数同时出现、不适用参数。 | 是，修正参数后重试。 |
| `INVALID_CURSOR` | cursor 无法解析、版本未知、类型与目标不匹配。 | 是，去掉 cursor 后重读。 |
| `PATH_NOT_FOUND` | 读取目标不存在。 | 视调用方修正路径而定。 |
| `FILE_NOT_FOUND` | 带写入前置条件但目标已消失。 | 是，需要重新读取状态。 |
| `FILE_CHANGED` | cursor 或 `expected_version` 对应的资源已变化。 | 是，需要重新读取。 |
| `TARGET_IS_DIRECTORY` | `write` 目标是目录。 | 是，需要修正目标文件路径。 |
| `UNSUPPORTED_TEXT_ENCODING` | 文本不是支持的 UTF-8/UTF-8 BOM。 | 否。 |
| `UNSUPPORTED_FILE_TYPE` | `read` 目标不是文本、目录或支持图片。 | 否。 |
| `UNSUPPORTED_IMAGE_FORMAT` | 图片扩展名、MIME 或签名不一致。 | 否。 |
| `FILE_TOO_LARGE` | 图片、写入内容或单个目录条目超过本地硬限制。 | 是，可改用其他处理方式。 |
| `READ_FILE_FAILED` | 已验证参数下发生文件读取错误。 | 视具体错误而定。 |
| `WRITE_FILE_FAILED` | 临时文件创建、刷盘或原子替换失败。 | 视具体错误而定。 |
| `CREATE_DIRECTORY_FAILED` | 自动创建父目录失败。 | 视权限或路径修正而定。 |

禁止把系统绝对路径、堆栈或任意异常文本直接作为面向模型的主要错误消息；必要诊断信息放在受控 `details` 字段。

## 9. 实施阶段

### 阶段 0：冻结契约并建立缺陷基线

**目的**：先证明当前缺陷，并把新接口写成测试可执行的规范。

**改动**

1. 新增独立的 Tool 行为测试文件，避免继续把所有内置工具测试堆在 `test_tool_result_contract.py`。
2. 为以下已确认缺陷增加失败测试：
   - `read(limit=-1)` 读取全文；
   - 超长单行突破按行读取预期；
   - 目录无分页；
   - 图片无大小限制；
   - `write("new-dir/")` 创建空文件；
   - 覆盖期间失败会破坏原文件；
   - 参数 Schema 声明与本地实际校验不一致。
3. 用契约测试固定第 6 节输入、结果和错误码。

**主要文件**

- 新增：`tests/tools/test_read_tool.py`
- 新增：`tests/tools/test_write_tool.py`
- 新增或修改：`tests/tools/test_tool_argument_validation.py`
- 保留并适当拆分：`tests/test_tool_result_contract.py`

**验收**

- [ ] 新测试能在旧实现上稳定失败，并准确对应上述缺陷。
- [ ] 现有权限与 Runtime 测试仍通过。
- [ ] 测试使用临时目录，不读取或修改开发者真实文件。

### 阶段 1：建立 Tool 参数解析边界

**目的**：让模型参数在权限判断前成为可信的内部数据，避免只依赖 JSON Schema。

**改动**

1. 在 `Tool` 增加可选参数解析器，放在现有字段末尾并提供默认值，避免破坏其他工具的构造调用。
2. `Tools.prepare_call()` 按固定顺序执行：解析 JSON 对象 -> 调用参数解析器 -> 构造权限请求。
3. 解析器必须返回新字典，不能原地修改调用方字典。
4. 解析器产生的 `TypeError/ValueError` 统一转换为 `ToolCallPreparationError(ToolError("INVALID_ARGUMENTS", ...))`。
5. 为 `read/write` 增加专用参数解析函数，严格拒绝布尔值冒充整数、未知字段、空路径和错误类型。
6. 更新 Tool JSON Schema：整数使用 `integer`，设置 `minimum`；`content` 在 `write` 中改为必填；新增 cursor/version 字段及互斥规则的描述。

**主要文件**

- 修改：`code/agent/tools/types.py`
- 修改：`code/agent/tools/tools.py`
- 修改：`code/agent/tools/read.py`
- 修改：`code/agent/tools/write.py`
- 修改：`tests/test_tool_preparation.py`
- 新增/修改：`tests/tools/test_tool_argument_validation.py`

**验收**

- [ ] 非对象参数、未知字段、负数、零、浮点数和布尔值在权限判断前返回 `INVALID_ARGUMENTS`。
- [ ] 权限请求和执行拿到的是同一份解析后参数。
- [ ] `edit/bash` 未配置解析器时行为保持不变。

### 阶段 2：实现 Read 文本双重限制与 Cursor

**目的**：兼顾普通源码的按行可读性和超长单行文件的字符硬限制。

**改动**

1. 删除旧 `offset` 文本接口，使用 `start_line/cursor/limit`。
2. 使用流式文本读取，不允许为了分页先 `file.read()` 全文。
3. 首次读取可扫描到 `start_line`；后续读取通过 cursor 中的文本流位置继续，避免每次从文件开头重扫。
4. 每次读取同时维护行片段计数和字符计数；达到任一上限立即停止。
5. 使用文本流的安全位置 cookie 或等价的增量解码状态，确保 UTF-8 多字节字符不被截断。
6. 读取前、读取后和 cursor 恢复时检查文件版本。
7. 明确支持 UTF-8 与 UTF-8 BOM；编码失败返回 `UNSUPPORTED_TEXT_ENCODING`。
8. 返回 `truncated`、`truncation_reason`、`continues_line` 和 `next_cursor`。

**主要文件**

- 修改：`code/agent/tools/read.py`
- 可新增：`code/agent/tools/read_cursor.py`，仅在 cursor 编解码和版本校验使 `read.py` 明显复杂时提取。
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_read_tool.py`

**验收**

- [ ] 普通多行 UTF-8 文件按行范围读取。
- [ ] 单行超过 20,000 字符时只返回本地允许的字符数，并能无重复、无缺失地续读。
- [ ] 中文字符不会被 cursor 切坏。
- [ ] 文件在两次读取间变化时旧 cursor 返回 `FILE_CHANGED`。
- [ ] 无 cursor 的 `start_line` 和带 cursor 的续读都不一次性加载全文。

### 阶段 3：完成 Read 目录与图片限制

**目的**：让所有 `read` 返回类型都受本地资源边界约束，而不是只限制文本。

**改动**

1. 目录条目稳定排序并分页，返回标准 `entries`、`truncated` 和 `next_cursor`。
2. 在添加每个目录条目前估算/计算序列化字符量，达到 `max_tool_call_length` 时停止。
3. 目录 cursor 保存下一索引和目录版本；目录变化后拒绝旧 cursor。
4. 使用 `os.scandir()` 获取条目类型，显式标记符号链接，不在列目录阶段递归跟随。
5. 图片先 `stat` 后读取；超过 `max_image_bytes` 直接失败。
6. 对允许的图片格式执行轻量签名校验，再构造 `Attachment`。
7. 对普通二进制文件返回 `UNSUPPORTED_FILE_TYPE`，不尝试用替换字符伪装成文本。

**主要文件**

- 修改：`code/agent/tools/read.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_read_tool.py`
- 修改：`tests/test_tool_result_contract.py`

**验收**

- [ ] 大目录不会一次进入 Context，并可通过 cursor 完整遍历。
- [ ] 目录结果的条目数和字符数均不能突破本地上限。
- [ ] 超大图片不会被读入内存。
- [ ] 伪装扩展名的图片和普通二进制文件得到稳定错误。
- [ ] 合法图片仍通过现有 Attachment 适配进入模型输入。

### 检查点 A：Read 完整性

- [ ] `read` 文本、目录、图片的契约测试全部通过。
- [ ] `tests/test_tool_preparation.py` 和权限测试通过。
- [ ] 使用普通源码、中文文件、单行压缩文件、大目录和图片进行手动临时目录验证。
- [ ] 确认每一种成功返回都受至少一个本地硬限制约束。

### 阶段 4：收缩 Write 职责并实现原子写入

**目的**：消除目录猜测和非原子覆盖，建立稳定的完整文件写入语义。

**改动**

1. 删除根据末尾 `/` 或 `\\` 判断目录的分支；`write` 永远把 `target_path` 视为文件。
2. `content` 改为必填字符串，允许显式传空字符串以创建空文件。
3. 目标是现有目录时返回 `TARGET_IS_DIRECTORY`。
4. 将 `content` 编码为 UTF-8 后检查 `max_write_bytes`，超限返回 `FILE_TOO_LARGE`，不得创建父目录或临时文件。
5. 父目录不存在时继续通过 `os.makedirs(..., exist_ok=True)` 创建。
6. 在目标同目录创建唯一临时文件，写入内容、flush、必要时 `os.fsync()`，再通过 `os.replace()` 原子替换。
7. 替换现有文件时尽量保留原权限位；不得复制所有者或 ACL 等平台特定元数据，相关限制写入风险说明。
8. 所有失败路径清理本次创建的临时文件，且不得删除或截断原目标。
9. 成功后返回 `created/replaced`、`bytes_written` 和新 `version`。

**主要文件**

- 修改：`code/agent/tools/write.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_write_tool.py`
- 修改：`tests/test_tool_result_contract.py`

**验收**

- [ ] `write("new-dir/")` 不再创建被误判的空文件；目标语义始终是文件。
- [ ] 自动创建多层父目录后可成功写文件。
- [ ] 注入写入失败或替换失败时，原文件内容保持不变且临时文件被清理。
- [ ] 中文内容的 `bytes_written` 等于 UTF-8 实际字节数。
- [ ] 空字符串能创建或清空文件，但必须由调用方显式提供 `content`。

### 阶段 5：增加 Write 文件版本前置条件

**目的**：降低 Agent 基于旧内容覆盖用户或另一个 Session 新修改的风险。

**改动**

1. 抽取 `read/write` 共用的文件版本 token 生成与校验函数；只有出现真实重复后才单独建模块。
2. `write(expected_version=...)` 在创建临时文件前检查当前目标状态。
3. 在 `os.replace()` 前再次检查目标版本，缩小“校验后被修改”的竞态窗口。
4. 目标版本不一致、目标消失或目标意外出现均返回 `FILE_CHANGED`，并清理临时文件。
5. 未提供 `expected_version` 时保留覆盖能力，但结果明确返回未执行版本前置检查。

**主要文件**

- 修改：`code/agent/tools/read.py`
- 修改：`code/agent/tools/write.py`
- 可新增：`code/agent/tools/files/version.py`
- 修改：`tests/tools/test_read_tool.py`
- 修改：`tests/tools/test_write_tool.py`

**验收**

- [ ] `read` 返回的版本可直接用于后续 `write`。
- [ ] 文件未变化时带版本写入成功。
- [ ] 文件被外部修改后，旧版本写入返回 `FILE_CHANGED` 且不覆盖新内容。
- [ ] 新建文件和无前置条件覆盖的既有行为有明确测试。

### 阶段 6：集成收口与文档更新

**目的**：删除旧契约痕迹，确认 Runtime、Context 和权限链没有回归。

**改动**

1. 更新内置 Tool 描述，使模型明确知道 cursor、行数限制、本地字符硬限制和 `expected_version`。
2. 搜索并更新所有直接调用旧 `read(offset, limit)` 或依赖 `make_directory` 结果的代码和测试。
3. 删除旧 `listdir`、`offset`、`make_directory` 等返回字段的兼容分支，不保留双协议。
4. 在工具开发文档中记录最终契约、错误码、默认限制和示例。
5. 运行完整工具、权限、Runtime、Session 和 Web Server 测试，确认 SSE 工具事件和 Context 持久化仍能序列化新结果。

**主要文件**

- 修改：`code/agent/tools/read.py`
- 修改：`code/agent/tools/write.py`
- 修改：所有命中的直接调用方和相关文档
- 修改：`tests/test_tool_result_contract.py`
- 修改：`tests/test_tool_preparation.py`
- 必要时修改：`client/web/server/tests/test_runs_api.py`

**验收**

- [x] 仓库中不存在仍被使用的旧 `read` 分页参数和 `write` 目录创建语义。
- [x] 新 Tool Schema 与本地参数解析行为一致。
- [x] 工具结果可编码、持久化、恢复并再次发送给模型。
- [x] `read/write` 的所有失败均通过 `ToolResult` 返回，不让预期业务错误逃逸为未处理异常。
- [x] `git diff --check`、相关测试和全量测试通过。

## 10. 测试矩阵

### 10.1 Read 文本

- 普通 ASCII 多行文件。
- 含中文、emoji、组合字符和 UTF-8 BOM 的多行文件。
- 单行长度小于、等于和大于 `max_tool_call_length`。
- 文件末尾无换行。
- 空文件。
- `start_line` 位于开头、中间、末尾和文件范围外。
- cursor 连续读取可无重复、无缺失地重建原内容。
- cursor 被篡改、类型不匹配、目标文件变化。
- 非 UTF-8 文本和含 NUL 的二进制文件。
- `limit` 为负数、零、浮点数、布尔值、字符串和超大正整数。

### 10.2 Read 目录与图片

- 空目录、普通目录、超过条目上限的大目录。
- 大小写名称排序、隐藏文件、符号链接和其他类型条目。
- 目录在分页之间增加、删除或重命名条目。
- 合法 PNG/JPEG/GIF/WebP/BMP。
- 扩展名与签名不一致、未知图片扩展名、超大图片。
- 目录结果序列化字符量先于条目上限触发截断。

### 10.3 Write

- 创建新文件、替换现有文件、写入空字符串。
- 自动创建一级和多级父目录。
- 目标是目录、父路径是文件、只读目录和无效路径。
- ASCII、中文和 emoji 的实际 UTF-8 字节数。
- 内容小于、等于和大于 `max_write_bytes`。
- 临时文件写入失败、flush 失败、`os.replace()` 失败后的原文件完整性和清理。
- 正确版本、过期版本、目标消失和目标意外出现。
- Windows 与 macOS/Linux 路径分隔符和替换行为。

### 10.4 集成

- `prepare_call -> permission check -> execute -> encode_result` 完整链路。
- `plan/build/yolo` 对 workspace 内外 `read/write` 的现有权限语义不变。
- 权限确认后的目标路径复检仍有效。
- 新结果进入 Context、数据库历史和恢复流程后结构不丢失。

## 11. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| Cursor 设计过于复杂 | 难维护，边界 bug 增多 | 使用无状态、版本化、单模块编解码；调用方只看到字符串。 |
| 文件在检查与实际 I/O 间变化 | 读取拼接错误或覆盖新内容 | 读取前后检查版本；写入前和替换前检查版本；承认这不是 OS 沙箱。 |
| 目录稳定排序需要收集全部名称 | 超大目录仍有 CPU/内存成本 | 限制返回内容；后续如出现真实超大目录场景，再引入平台目录游标或取消全量排序。 |
| 原子替换不保留全部平台元数据 | ACL、扩展属性可能变化 | 首期只承诺内容原子性和基本权限位；平台元数据另立需求。 |
| Windows 文件被占用时 `os.replace()` 失败 | 写入无法完成 | 返回稳定 `WRITE_FILE_FAILED`，保留原文件并清理临时文件。 |
| 默认上限不适合个别项目 | 大文件需要更多续读或无法一次写入 | 上限集中在 `ExecutionContext`，允许未来通过 Session/宿主配置调整，不允许模型直接提高。 |
| 旧模型上下文包含旧 Tool Schema | 一轮内可能产生旧参数 | 新 Run 构造 Runtime 时使用新 Schema；部署时不恢复运行中的 pending 旧调用，必要时取消旧 Run。 |

## 12. 推荐实施顺序与提交边界

建议按以下顺序独立完成，每一步保持测试可运行：

1. 参数解析边界与缺陷测试。
2. Read 文本双重限制和 cursor。
3. Read 目录、图片限制。
4. Write 单一职责和原子写入。
5. 文件版本前置条件。
6. 删除旧契约并完成集成回归。

不要在同一个提交中同时重构 `edit/bash`。它们可复用阶段 1 建立的参数解析边界，但应在各自计划中独立迁移和验收。

## 13. 完成定义

只有同时满足以下条件，计划才算完成：

- [x] `read` 的文本、目录和图片结果均有本地不可绕过的硬限制。
- [x] 超长单行文件可以通过 cursor 无损续读。
- [x] `write` 不再创建目录或依赖路径末尾分隔符猜测类型。
- [x] `write` 使用同目录临时文件和原子替换，失败不破坏原文件。
- [x] `read` 版本可用于 `write` 并发前置检查。
- [x] 所有外部参数在权限检查前经过本地类型和范围校验。
- [x] 新增边界测试、集成测试和错误码测试全部通过。
- [x] 旧接口和兼容分支已删除，文档与 Tool Schema 只描述最终协议。

## 14. 实施记录

### 已完成：阶段 0-3（Read）

- `Tool.argument_parser` 已在权限请求构造前执行，`read` 参数以 `target_path`、`cursor`、`start_line`、`limit` 为唯一协议；不保留 `offset` 兼容分支。
- 文本读取同时受行片段上限和 `max_tool_call_length` 字符上限控制。超长单行使用带文件版本、文本位置和行状态的 cursor 无损续读。
- 目录使用 `os.scandir()`、稳定排序、版本化 cursor 和本地条目/字符上限；无法容纳单个条目时返回 `FILE_TOO_LARGE`，避免生成不能推进的 cursor。
- 图片先检查本地 `max_image_bytes`，再校验扩展名与 PNG/JPEG/GIF/WebP/BMP 签名，成功结果附带大小和版本。

### 已完成：阶段 4-5（Write）

- `write` 只创建或完整替换文本文件，`content` 为必填字符串；目标目录返回 `TARGET_IS_DIRECTORY`，不再按路径末尾分隔符创建目录。
- 写入前以 UTF-8 字节数执行 `max_write_bytes` 硬限制，随后自动创建父目录。
- 写入通过同目录临时文件、`flush`、`fsync` 和 `os.replace()` 完成；失败清理临时文件且不截断原文件，并尽量保留原基本权限位。
- `read` 与 `write` 共用 `tools/files/version.py` 的不透明文件版本 token。`expected_version` 会在临时文件创建前和 `os.replace()` 前复核；目标变化、出现或消失均返回 `FILE_CHANGED`。

### 已验证

- `pytest -q tests/tools/test_read_tool.py tests/tools/test_write_tool.py tests/tools/test_tool_argument_validation.py tests/test_tool_preparation.py tests/test_tool_result_contract.py`：42 passed。
- `pytest -q tests/test_permission_policies.py tests/test_tool_preparation.py tests/test_permission_manager.py tests/test_permission_persistence.py tests/test_runtime_permissions.py tests/storage/test_session_permission_rule_repository.py tests/storage/test_migrations.py`：48 passed。
- `git diff --check`：通过。
- 全量 `pytest -q`：248 passed。

### 已完成：阶段 6（集成收口）

- 已确认生产代码和测试调用方只使用新的 `read`/`write` 契约，没有仍在使用的 `offset`、`listdir` 或 `make_directory` 字段。
- 已确认 `Tools.prepare_call -> PermissionManager -> Tools.execute -> Tools.encode_result` 链路可处理新的分页、图片附件、原子写入和结构化错误结果。
- 修正了三个仍按旧权限假设编写的 Runtime 测试夹具：Build 模式下工作区内写入应直接允许，需要验证权限暂停时使用工作区外路径。
- 已通过 `python -m compileall -q code/agent/tools code/agent/session` 和 `git diff --check`。
