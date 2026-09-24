# Edit 工具优化迭代计划

## 1. 计划状态

- 当前状态：待开发。
- 适用范围：`edit` Tool、与其共享的文件版本/原子提交能力、`write` 对同文件并发提交的协同，以及相关 Tool、Runtime、权限测试。
- 不包含：`read` 的分页契约变更、`bash`/`MCP` 的重构、自动三方合并、跨进程分布式锁和 Web UI 改动。

## 2. 背景与当前缺陷

`edit` 的职责应是：基于 Agent 刚刚读取到的指定文件版本，对其中可验证的文本片段做局部替换。它不应成为无条件覆盖文件的第二个 `write`。

当前 [edit.py](../../code/agent/tools/edit.py) 存在以下问题：

1. 没有 `argument_parser`。JSON Schema 之外没有本地类型、字段和范围校验，错误模型参数可能进入执行层并变成笼统的 `TOOL_EXECUTION_FAILED`。
2. 没有 `expected_version`。Agent 读取文件到执行编辑之间，用户、另一个 Session 或 Agent 的修改可能被静默覆盖。
3. 使用 `open(..., "w")` 直接覆盖原文件。写入、刷盘或进程中断失败时，原文件可能被截断或损坏。
4. 没有文件大小上限，会把任意大文件完整读入内存。
5. `old_text`、`new_text`、`replace_all` 使用 `or` 静默兜底：缺失字段、错误类型和空文本会混淆为同一行为。
6. 匹配失败会把完整 `old_text` 拼到错误消息中，可能把大段或敏感文本重新发送给模型。
7. 多条编辑按顺序应用的行为没有明确契约；没有“全部先验证成功，再提交”的测试保证。
8. `write` 已具备版本前置条件和原子替换，但没有与 `edit` 共享提交锁；同一服务进程内两个 Agent 对同一文件提交时仍可能在版本复检和 `os.replace()` 间竞争。

## 3. 目标

1. `edit` 只编辑已有 UTF-8 文本文件；不创建文件、不创建目录、不处理图片或任意二进制文件。
2. 每次 `edit` 必须携带来自 `read` 的 `expected_version`，不允许基于未知版本盲改文件。
3. 所有模型参数在权限判断前完成本地校验和规范化。
4. 所有编辑先在内存副本上按顺序应用；任一编辑不适用时，原文件不得发生变化。
5. `edit` 与 `write` 使用同一条“按文件串行提交 + 版本复检 + 临时文件原子替换”路径。
6. 同一 Python 服务进程中，多个 Agent 对同一路径的提交必须串行化；后提交且版本过期的请求返回 `FILE_CHANGED`。
7. 文件源内容与最终写入内容均受本地硬上限约束，不能依赖第三方 LLM 服务端限制。

## 4. 非目标

1. 不根据行号或字节偏移编辑；局部替换继续以明确的 `old_text` 为锚点。
2. 不自动把两个 Agent 的冲突编辑合并。发现过期版本后，由 Agent 重新读取、重新判断并生成下一次编辑。
3. 不让 `replace_all=false` 在多处匹配时“猜一个”替换。
4. 不在模型思考期间持锁，避免一个慢模型阻塞其他文件操作。
5. 首期不承诺多个独立进程、多个桌面实例或外部编辑器之间的强一致排他锁；这些场景后续单列跨进程锁需求。
6. 不保留当前 `edit` 的宽松参数兼容逻辑；迁移后只保留本计划定义的新契约。

## 5. 架构决策

### 5.1 强制 `expected_version`

`edit` 是对已读取文本的局部变换。与完整覆盖的 `write` 不同，它天然依赖源文件内容，因此 `expected_version` 设为必填字段：

```json
{
  "target_path": "src/app.py",
  "expected_version": "read 返回的 version",
  "edits": [
    {
      "old_text": "return old_value",
      "new_text": "return new_value",
      "replace_all": false
    }
  ]
}
```

这保证模型先使用 `read` 获得当前内容和版本，再执行局部修改。版本不匹配时返回 `FILE_CHANGED`，不做隐式重试。

### 5.2 乐观版本校验与提交锁并用

仅有版本校验不能完全消除同一进程内的 TOCTOU 窗口。最终提交流程为：

```text
read 得到 version=v1
        ↓
Agent 生成 edit 参数
        ↓
Tools.prepare_call 解析参数并检查 Session 权限
        ↓
按规范化绝对路径获取进程内阻塞锁（有超时，不自旋）
        ↓
再次读取当前版本；不是 v1 则 FILE_CHANGED
        ↓
读取并校验 UTF-8 文件，内存中顺序应用全部 edits
        ↓
写入同目录临时文件，flush + fsync
        ↓
替换前再复检版本；仍是 v1 才 os.replace
        ↓
释放锁，返回新 version
```

例如 Agent A、B 都基于 `v1` 编辑：A 先提交并产生 `v2`；B 获锁后发现文件不是 `v1`，得到 `FILE_CHANGED`，不能覆盖 A。

锁使用标准库阻塞同步原语，按规范化绝对路径维护，设置有限等待时间；超时返回 `FILE_BUSY`（`retryable=true`）。禁止使用自旋锁。

### 5.3 共享提交模块

当前 `write` 已实现临时文件和版本复检。`edit` 若复制这段逻辑会使两个 Tool 的安全边界逐渐分叉。因此抽取一个内部文件提交模块，例如：

```text
tools/file_version.py       # 保持版本 token 定义
tools/file_mutation.py      # 新增：按路径提交协调、原子替换、版本复检、权限位保留
tools/write.py              # 组装完整 content，调用共享提交模块
tools/edit.py               # 组装编辑后的 content，调用共享提交模块
```

该模块不依赖 `ToolResult`，只返回明确的提交结果或受控异常。`write/edit` 各自决定 API 参数、业务错误码和结果字段。

### 5.4 文本与大小边界

在 `ExecutionContext` 新增：

| 配置 | 默认值 | 用途 |
| --- | --- | --- |
| `max_edit_source_bytes` | 2 MiB | `edit` 允许完整加载的源文件最大字节数。 |
| `max_write_bytes` | 2 MiB | 编辑后的 UTF-8 内容最大字节数，沿用现有 `write` 上限。 |
| `file_mutation_lock_timeout_seconds` | 5 秒 | 同一进程内等待目标文件提交锁的最长时间。 |

执行时先 `stat` 检查源文件大小，再以严格 UTF-8 解码。含 NUL 的文件返回 `UNSUPPORTED_FILE_TYPE`；解码失败返回 `UNSUPPORTED_TEXT_ENCODING`。应保留原始换行形式和 UTF-8 BOM 字节，不能因为局部编辑意外改写全文件格式。

## 6. 最终 Edit 契约

### 6.1 输入

```json
{
  "target_path": "src/app.py",
  "expected_version": "eyJkZXZpY2UiOj...",
  "edits": [
    {
      "old_text": "const enabled = false;",
      "new_text": "const enabled = true;",
      "replace_all": false
    }
  ]
}
```

字段规则：

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `target_path` | 是 | 非空字符串；路径解析和权限检查沿用 `Tools.prepare_call()`。 |
| `expected_version` | 是 | 非空字符串，必须等于当前目标文件的 `file_version`。 |
| `edits` | 是 | 非空数组，最多 `ctx.max_edit_operations` 条（新增，默认 100）。 |
| `edits[].old_text` | 是 | 非空字符串。 |
| `edits[].new_text` | 是 | 字符串，可为空，用于删除文本。 |
| `edits[].replace_all` | 否 | 严格布尔值，默认 `false`。 |

顶层和每一条 edit 均拒绝未知字段。布尔、整数、`null` 不得被静默转换为文本或开关值。

### 6.2 匹配与顺序语义

1. 编辑按数组顺序在内存中的当前内容上执行。
2. `replace_all=false`：`old_text` 必须恰好出现一次；零次返回 `EDIT_TEXT_NOT_FOUND`，多次返回 `EDIT_TEXT_AMBIGUOUS`。
3. `replace_all=true`：`old_text` 至少出现一次；匹配的全部文本替换为 `new_text`。
4. 后续 edit 可以依赖前一个 edit 的替换结果。这是明确支持的顺序语义。
5. 任一条编辑失败时，整体失败；不写临时文件、不修改原文件。

### 6.3 成功结果

```json
{
  "operation": "edited",
  "path": "/workspace/src/app.py",
  "edit_count": 2,
  "replacement_count": 3,
  "bytes_written": 1420,
  "version": "...",
  "precondition_checked": true
}
```

### 6.4 稳定错误码

| 错误码 | 场景 | retryable |
| --- | --- | --- |
| `INVALID_ARGUMENTS` | 参数类型、缺失、范围、未知字段错误。 | 是 |
| `FILE_NOT_FOUND` | 目标不存在或不是普通文件。 | 是 |
| `TARGET_IS_DIRECTORY` | 目标是目录。 | 是 |
| `FILE_CHANGED` | `expected_version` 过期，或提交前文件发生变化。 | 是 |
| `FILE_BUSY` | 指定时间内未获取当前进程的目标文件提交锁。 | 是 |
| `EDIT_TEXT_NOT_FOUND` | 某条 `old_text` 没有匹配。 | 是 |
| `EDIT_TEXT_AMBIGUOUS` | `replace_all=false` 时匹配多处。 | 是 |
| `UNSUPPORTED_TEXT_ENCODING` | 文件不是 UTF-8。 | 否 |
| `UNSUPPORTED_FILE_TYPE` | 文件含 NUL 或不是可编辑文本。 | 否 |
| `FILE_TOO_LARGE` | 源文件或编辑后内容超过本地硬上限。 | 是 |
| `EDIT_FILE_FAILED` | 受控 I/O、临时文件或替换失败。 | 视情况而定 |

错误消息不能包含完整 `old_text`、完整文件内容、底层异常文本或堆栈。`details` 最多包含路径、编辑序号、匹配数和本地限制值。

## 7. 实施阶段

### 阶段 0：建立 Edit 缺陷基线

**目的**：先把当前危险行为变成可重复的失败测试，避免实现时遗漏边界。

**改动**：

1. 新增 `tests/tools/test_edit_tool.py`。
2. 编写失败测试：未知字段、错误类型、空 `old_text`、空 edits、重复文本、无匹配文本、删除文本、多条顺序编辑。
3. 编写失败测试：文件过大、非 UTF-8、NUL、目标目录、过期版本、临时替换失败、编辑失败不得改动原文件。
4. 编写两个同版本编辑请求的并发测试，为后续锁实现定义结果：一个成功，另一个 `FILE_CHANGED`。

**主要文件**：

- 新增：`tests/tools/test_edit_tool.py`
- 修改：`tests/test_tool_result_contract.py`

**验收**：

- [ ] 新测试在旧 `edit` 上稳定失败。
- [ ] 测试只使用临时目录，不访问真实工作目录。

### 阶段 1：建立严格参数边界

**目的**：让参数在权限判断前成为可信内部数据。

**改动**：

1. 实现 `parse_edit_arguments()`，作为 `REGISTER.argument_parser`。
2. 更新 Edit JSON Schema：`expected_version`、`edits[].old_text`、`edits[].new_text` 为必填；明确 `replace_all` 默认值和约束。
3. 在 `ExecutionContext` 新增 `max_edit_operations`，并校验全部新增限制大于零。
4. 更新参数解析测试，确认 `PreparedToolCall.arguments` 和权限资源来自解析后的参数。

**主要文件**：

- 修改：`code/agent/tools/edit.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_edit_tool.py`
- 必要时修改：`tests/tools/test_tool_argument_validation.py`

**验收**：

- [ ] 非法参数在权限弹窗前返回 `INVALID_ARGUMENTS`。
- [ ] 合法空 `new_text` 被保留为删除语义，不被转成缺失值。
- [ ] `expected_version` 缺失不能进入执行层。

### 阶段 2：实现受限文本变换

**目的**：在不写入磁盘前完整验证编辑列表，保证 all-or-nothing 语义。

**改动**：

1. `stat` 后检查 `max_edit_source_bytes`，超过上限立即返回 `FILE_TOO_LARGE`。
2. 以严格 UTF-8 加载文件，保留 BOM 和换行；拒绝 NUL 和不支持编码。
3. 将唯一匹配逻辑改为返回匹配数量而不是抛出含原文的通用异常。
4. 顺序应用所有 edits，累计替换数量；任一失败直接返回稳定错误码。
5. 编辑后再次检查 UTF-8 字节数，超过 `max_write_bytes` 返回 `FILE_TOO_LARGE`。

**主要文件**：

- 修改：`code/agent/tools/edit.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_edit_tool.py`

**验收**：

- [ ] 所有编辑成功前，原文件字节内容保持不变。
- [ ] 唯一替换、全量替换、删除、顺序依赖和失败回滚均有测试。
- [ ] 原文件编码、BOM 和换行不会被无关地改变。

### 阶段 3：抽取共享安全提交路径

**目的**：使 `write/edit` 不复制版本检查、原子替换和权限位保留逻辑。

**改动**：

1. 新增内部模块 `code/agent/tools/file_mutation.py`。
2. 从 `write.py` 提取：既有文件版本读取、基本权限位保留、同目录临时文件写入、`flush`、`fsync`、替换前版本复检、`os.replace` 和临时文件清理。
3. 共享模块接收路径、期望版本和已编码 bytes；不处理 Tool 参数、不生成 `ToolResult`。
4. `write` 迁移到共享模块，保持已有输入/输出契约和测试结果不变。
5. `edit` 调用同一模块，并将提交失败映射为 `FILE_CHANGED` 或 `EDIT_FILE_FAILED`。

**主要文件**：

- 新增：`code/agent/tools/file_mutation.py`
- 修改：`code/agent/tools/write.py`
- 修改：`code/agent/tools/edit.py`
- 修改：`tests/tools/test_write_tool.py`
- 修改：`tests/tools/test_edit_tool.py`

**验收**：

- [ ] `write` 现有原子替换、版本冲突和权限位测试全部通过。
- [ ] `edit` 在 `os.replace()` 失败时原文件不变，临时文件被清理。
- [ ] `read` 返回的版本可直接传给 `edit`。

### 阶段 4：加入同进程文件提交协调

**目的**：消除同一服务进程内 `expected_version` 复检到替换之间的竞争窗口。

**改动**：

1. 在 `file_mutation.py` 实现按真实绝对路径键控的锁注册表。
2. 使用阻塞锁加有限超时；不能获得锁时返回受控的 `FILE_BUSY`，禁止循环占用 CPU。
3. 锁范围严格限制为版本检查、临时文件写入和原子替换；不覆盖模型调用、权限弹窗或文本生成。
4. 同一目标的 `write` 和 `edit` 必须共用该协调器；不同文件可并行提交。
5. 对锁条目做无引用清理，避免长期运行的桌面进程因历史路径无限增长。

**主要文件**：

- 修改：`code/agent/tools/file_mutation.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_write_tool.py`
- 修改：`tests/tools/test_edit_tool.py`

**验收**：

- [ ] 两个同版本、同路径提交中，最多一个成功；另一个返回 `FILE_CHANGED`。
- [ ] 对不同路径的提交不会互相阻塞。
- [ ] 锁超时返回 `FILE_BUSY`，并且没有自旋等待。

### 检查点 A：文件修改安全性

- [ ] `read/write/edit` 的版本 token、冲突码和原子替换测试通过。
- [ ] 同一进程多 Agent 冲突测试通过。
- [ ] 现有 Session 权限测试和 Tool 结果编码测试通过。

### 阶段 5：Runtime 集成与文档收口

**目的**：让模型了解新契约，并确认 Tool 结果可正常进入 Context、持久化和恢复链路。

**改动**：

1. 更新 Edit 工具描述，要求先 `read`，再携带 `version` 调用 `edit`。
2. 搜索并删除旧 Edit 的 `EMPTY_FILE`、`EMPTY_EDITS`、异常原文泄露等契约痕迹。
3. 更新工具结果契约测试和需要的 Runtime 测试。
4. 在本计划记录最终错误码、锁边界和跨进程限制。
5. 运行完整测试和 `git diff --check`。

**主要文件**：

- 修改：`code/agent/tools/edit.py`
- 修改：`tests/test_tool_result_contract.py`
- 必要时修改：`tests/test_runtime_permissions.py`
- 修改：本计划文档

**验收**：

- [ ] Tool Schema、本地解析器和 Tool 描述只表达最终契约。
- [ ] `prepare_call -> PermissionManager -> execute -> encode_result` 可处理 Edit 的成功、冲突和失败。
- [ ] 完整测试通过。

## 8. 测试矩阵

### 8.1 参数与权限

- 缺失 `target_path`、`expected_version`、`edits`、`old_text`、`new_text`。
- 空路径、空 `old_text`、空 edits、超出 edit 数量上限。
- `replace_all` 为字符串、整数、`null`、布尔值。
- 顶层和 edit 条目中的未知字段。
- 工作目录内外在 Plan/Build/YOLO 下的既有权限语义。

### 8.2 文本变换

- 唯一替换、全量替换、删除、追加式替换。
- 零处匹配、多处匹配、顺序依赖编辑。
- 空文件、UTF-8 BOM、CRLF、无末尾换行、中文和 emoji。
- 非 UTF-8、NUL、源文件超过限制、编辑结果超过限制。
- 任意一条编辑失败后原文件逐字节保持不变。

### 8.3 冲突与提交

- `read(version=v1) -> edit(expected_version=v1)` 成功。
- 外部修改后以 `v1` 编辑返回 `FILE_CHANGED`。
- 目标删除、目标替换、目标在提交期出现。
- 临时文件创建、写入、刷盘、替换失败时原文件保持不变且临时文件清理。
- 两个 Agent/两个线程同路径同版本提交。
- `write` 与 `edit` 同路径同版本交叉提交。
- 两个不同路径编辑可并行。

## 9. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| Agent 未先 read 就 edit | 无法确认定位正确性 | `expected_version` 强制必填；缺失直接拒绝。 |
| 大文件完整载入 | 内存和模型执行压力 | `stat` 前置检查 `max_edit_source_bytes`。 |
| 锁设计过度复杂 | 引入死锁、全局串行化 | 仅按路径锁、有限超时、短临界区、不同路径独立。 |
| 外部进程绕过进程内锁 | 仍可能产生极小跨进程竞态 | 替换前版本复检；明确首期限制；出现真实多进程需求后使用平台文件锁。 |
| 自动合并掩盖语义冲突 | 代码被错误拼接 | 首期只返回 `FILE_CHANGED`，由 Agent 重新读取决定。 |
| 抽取共享模块影响已稳定的 write | 回归风险 | 先锁定 Write 行为测试，再迁移；每阶段运行 Read/Write 回归。 |

## 10. 完成定义

- [ ] `edit` 参数在权限检查前通过严格本地解析。
- [ ] `edit` 必须使用 `read` 返回的 `expected_version`。
- [ ] 所有 edits 成功验证前，原文件绝不被修改。
- [ ] `edit` 与 `write` 使用共享的版本校验和原子提交路径。
- [ ] 同一进程的多个 Agent 对同一路径提交不会互相静默覆盖。
- [ ] 匹配错误不返回完整源文本或底层异常。
- [ ] 大文件、编码、临时写入失败和并发冲突均有自动化测试。
- [ ] 全量测试与 `git diff --check` 通过。
