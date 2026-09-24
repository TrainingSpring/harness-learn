# Bash 工具与持续进程优化迭代计划

## 1. 计划状态

- 当前状态：已完成（阶段 0-6）。
- 适用范围：一次性 Bash/PowerShell 命令、命令输出和超时控制、Session 内持续进程、日志读取、进程停止、相关权限与测试。
- 不包含：容器/虚拟机级沙箱、完整 Shell 语法分析、网络出站控制、跨应用重启恢复后台进程、用户显式脱离 Session 的守护服务。

## 2. 背景与当前缺陷

当前 [bash.py](../../code/agent/tools/bash.py) 已改为受本地边界保护的前台执行器；以下列表记录本计划启动时的缺陷基线：

1. 没有 `argument_parser`。空命令、非字符串命令、非法 timeout、未知字段都会越过参数准备阶段，可能在执行时变成笼统的 `TOOL_EXECUTION_FAILED`。
2. timeout 可省略且没有本地上限，曾允许无限等待。开发服务器、`tail -f`、交互式程序或挂起命令会长期占住 Agent Runtime。
3. 超时异常没有映射为稳定错误码；子进程及其后代也没有可靠地作为一组终止。
4. stdout/stderr 使用 `PIPE` 完整收集后才截断，超大输出会先占用本地内存。最后的兜底解码分支甚至不截断。
5. 返回值中的 `command` 在 Unix 是 argv 数组，在 Windows 是拼接字符串；无法稳定表达用户原始命令、实际 shell、工作目录和是否截断。
6. Windows 通过字符串拼接构造 PowerShell 命令，参数边界不明确；macOS/Linux 与 Windows 的进程终止策略也没有统一抽象。
7. 直接继承宿主完整环境变量，命令可能取得本不应暴露的凭据或服务端配置。
8. 现有 `BASH_EXECUTE` 的权限请求没有资源路径。当前仍只能按“是否执行 Bash”做整体授权；本计划明确记录这一限制，不把 Shell 文本误判为可精确授权的文件路径。
9. 启动服务、持续 worker、日志监听被迫通过“不设 timeout”或 `tail -f` 实现，既卡住 Agent Loop，又无法分页读取、检查状态或停止进程。

## 3. 产品目标

### 3.1 一次性命令

`bash` 只负责有限时长的前台命令，例如 `git status`、测试、构建、安装依赖和单次脚本执行。每次执行都有本地默认 timeout 和最大 timeout，输出在读取过程中受本地硬上限保护。

### 3.2 持续进程

新增 Session 归属的 Process Manager，供 Agent 启动开发服务、worker 或持续任务。进程启动后立即返回 `process_id`，Agent 可独立查询状态、分页读取新增日志、等待有限时长或停止进程。

```text
process_start("npm run dev")
    -> process_id、pid、running/exited 状态、日志 cursor

process_logs(process_id, cursor)
    -> 新日志片段、next_cursor、是否截断

process_stop(process_id)
    -> 终止该进程组及其后代
```

`tail -f` 不再作为日志监听方案。日志由 Process Manager 捕获，`process_logs` 以 cursor 续读，单次返回仍受输出上限控制。

### 3.3 生命周期

1. 后台进程属于当前 Session，不属于 Agent，也不属于 Agent Runtime。
2. Session 中多个 Agent 可以查看和停止同一个 Session 的进程，但不能访问其他 Session 的进程。
3. 取消当前 Agent Loop 不停止已启动服务；显式停止、关闭 `SessionExecution` 或应用退出时统一清理该 Session 的全部后台进程。
4. 进程状态和日志缓冲仅存在当前桌面应用进程内；应用重启后不尝试恢复旧 PID，避免误操作 PID 重用的外部进程。
5. 首期不提供 `detach`。若未来需要服务在 Session 关闭后仍持续运行，应单列“脱离 Session 进程”设计，并要求额外确认与可见的管理 UI。

## 4. 架构决策

### 4.1 Bash 与 Process 的职责边界

| 能力 | `bash` | `process` |
| --- | --- | --- |
| 用途 | 有限的一次性前台命令 | 持续运行或需要后续管理的命令 |
| 等待方式 | 等到退出或 timeout | 启动即返回，不等待退出 |
| 输出 | 本次调用的受限 stdout/stderr | Session 内环形日志缓冲，cursor 续读 |
| timeout | 强制默认值和最大值 | 仅启动确认与 `wait` 使用有限等待 |
| 生命周期 | 调用结束即结束 | 显式 stop、Session 关闭或应用退出时结束 |
| 示例 | `pytest -q`、`git diff` | `npm run dev`、worker、日志采集服务 |

禁止把 `timeout=None` 当作后台服务能力；也禁止让 `bash` 自动猜测某命令是否应后台运行。调用方必须明确选择 `bash` 或 `process_start`。

### 4.2 Process Manager 的归属

新增 `SessionProcessManager`，放在 `session` 目录，由 `SessionExecution` 创建和持有。它保存该 Session 的进程注册表、日志缓冲和清理职责；每个成员 Runtime 使用同一实例。

为使 Tool 能访问这个 Session 服务，`ExecutionContext` 新增一个非持久化的 `process_manager` 协作对象引用。该引用在 `SessionService._create_runtimes()` 创建 Runtime 时注入；它不是 Agent 状态，也不写入数据库。这样 Agent 仍可跨 Session 复用，Session 才是进程所有者。

```text
SessionExecution
    └─ SessionProcessManager (每个打开的 Session 一份)
        ├─ ProcessRecord(process_id, pid, state, timestamps, command)
        ├─ stdout/stderr 环形缓冲区
        └─ 进程组终止与 Session 清理

Runtime -> Tools -> process_* Tool -> ctx.process_manager
```

### 4.3 进程工具接口

首期新增五个职责单一的 Tool：`process_start`、`process_status`、`process_logs`、`process_wait`、`process_stop`。当前 `Tool` 使用静态 `PermissionRequirement`，拆分后每个 Tool 可以直接声明自己的权限动作，不需要增加动态权限分派。

```json
{"command":"npm run dev"}                         // process_start
{"process_id":"proc_..."}                         // process_status
{"process_id":"proc_...","cursor":"...","limit":200} // process_logs
{"process_id":"proc_...","timeout":10}         // process_wait
{"process_id":"proc_..."}                         // process_stop
```

每个 Tool 都有独立的参数解析器和字段白名单；不允许把不同操作的字段混合为一个宽松 Schema。权限声明为：`process_start` 复用 `BASH_EXECUTE`，`process_status/process_logs/process_wait` 使用 `PROCESS_INSPECT`，`process_stop` 使用 `PROCESS_STOP`。

成功结果的稳定字段：

```json
{
  "process_id": "proc_01...",
  "state": "running",
  "pid": 12345,
  "command": "npm run dev",
  "shell": "bash",
  "cwd": "/workspace",
  "started_at": "..."
}
```

`logs` 额外返回 `stdout`、`stderr`、`next_cursor`、`truncated`、`cursor_expired` 和日志缓冲边界。日志中不会泄露宿主环境变量；它只反映进程自己输出的内容。

### 4.4 权限边界

Shell 不是可靠的文件路径声明语言。命令可能经由变量、脚本、解释器、`cd`、子进程和网络访问多种资源，因此首期不能假装能实现“工作目录内 Bash 自动允许、目录外 Bash 请求授权”。

1. 保留 `BASH_EXECUTE`：用于一次性 `bash` 以及 `process_start`，按 Session 权限模式整体决策。
2. `process_status`、`process_logs` 和 `process_wait` 只允许访问当前 Session 的 Process Manager 记录，不读取外部资源；新增 `PROCESS_INSPECT`，所有模式默认允许。
3. `process_stop` 只允许停止当前 Session 所有的进程；新增 `PROCESS_STOP`，所有模式默认允许，因为它只减少已启动进程的影响范围。
4. `plan` 拒绝 `BASH_EXECUTE`；`build` 请求确认；`yolo` 允许，但仍保留硬安全策略。
5. 现有 Bash 规则是 Session 级 `resource=None` 规则。用户选择“本会话允许/拒绝”后，影响该 Session 后续 Bash 和 Process Start，不影响其他 Session。

完整的“命令访问哪些文件、网络和子进程”控制需要操作系统级沙箱，属于后续独立计划。正则黑名单只能作为强制最低防线，不能宣传为完整 Shell 安全模型。

### 4.5 输出、超时与环境

新增 `ExecutionContext` 配置：

| 配置 | 默认值 | 用途 |
| --- | ---: | --- |
| `max_bash_command_chars` | 8,000 | 单次原始 Shell 命令最大字符数。 |
| `default_bash_timeout_seconds` | 30 | 调用未传 timeout 时的前台命令 timeout。 |
| `max_bash_timeout_seconds` | 600 | 前台命令允许请求的最大 timeout。 |
| `max_bash_output_bytes` | 256 KiB | 单个 Bash 调用 stdout 与 stderr 各自的本地捕获上限。 |
| `max_process_log_bytes` | 4 MiB | 每个后台进程 stdout 与 stderr 各自的环形日志缓冲上限。 |
| `max_process_log_return_chars` | 20,000 | `process_logs` 单次返回给模型的最大字符数。 |
| `process_startup_probe_seconds` | 0.2 | 启动后台进程后用于识别立即退出的短检查窗口。 |

输出读取必须并行消费 stdout 与 stderr，防止任一管道填满造成子进程死锁。每个流使用受限缓冲：保留可诊断的头部和尾部，超出部分丢弃并返回截断标记；不能先积累整个输出再截断。

命令环境使用平台最小运行环境白名单，而不是继承宿主全部 `os.environ`。Unix 至少保留 `PATH`、`HOME`、`USER`、`LANG`、`LC_ALL`、`TMPDIR`；Windows 保留 `SystemRoot`、`ComSpec`、`PATH`、`PATHEXT`、`TEMP`、`TMP`、`USERPROFILE` 等系统运行所需变量。LLM、数据库、云服务等敏感变量不自动传递。项目需要的额外变量应在后续作为显式 Session 配置处理，不自动加载 `.env`。

### 4.6 跨平台命令与终止

1. macOS/Linux：以 `['bash', '-lc', command]` 启动，`start_new_session=True` 建立新的进程组；超时或 stop 使用 `os.killpg()` 终止整个进程组。
2. Windows：以 `['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command]` 启动，不使用字符串拼接；创建独立进程组，并通过 Windows 平台适配器使用树形终止机制结束后代。
3. Tool 返回始终保留原始 `command` 字符串，并单独返回 `shell`，不返回平台内部 argv 作为公开契约。
4. 无法启动 shell、工作目录不存在、权限不足、进程已经不存在、超时、输出截断都映射到稳定错误码，不泄露底层异常文本或堆栈。

## 5. 最终契约

### 5.1 Bash 输入与结果

```json
{"command":"pytest -q","timeout":120}
```

字段规则：

| 字段 | 必填 | 规则 |
| --- | --- | --- |
| `command` | 是 | 非空字符串，不超过 `max_bash_command_chars`。 |
| `timeout` | 否 | 严格正数，不超过 `max_bash_timeout_seconds`；省略时使用默认值。 |

成功结果：

```json
{
  "command": "pytest -q",
  "shell": "bash",
  "cwd": "/workspace",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "...",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "timeout_seconds": 120
}
```

非零退出码仍是工具成功结果，表示命令已经正常结束，Agent 应依据 `exit_code` 与输出自行判断。执行层故障才是 `ToolResult.failure`。

稳定错误码：

| 错误码 | 场景 | retryable |
| --- | --- | --- |
| `INVALID_ARGUMENTS` | 参数缺失、类型错误、空命令、超限。 | 是 |
| `PROJECT_NOT_SELECTED` | 当前 Session 没有工作目录。 | 是 |
| `WORKSPACE_NOT_FOUND` | 已选择的工作目录已不存在或不是目录。 | 是 |
| `BASH_EXECUTABLE_NOT_FOUND` | Bash 或 PowerShell 无法找到。 | 否 |
| `BASH_START_FAILED` | 命令进程无法启动。 | 是 |
| `BASH_TIMEOUT` | 到达 timeout，进程组已经进入终止流程。 | 是 |
| `BASH_EXECUTION_FAILED` | 未分类的受控执行 I/O 失败。 | 视情况 |

### 5.2 Process 输入与结果

| operation | 必填字段 | 行为 |
| --- | --- | --- |
| `process_start` | `command` | 在当前工作目录异步启动进程并立即返回。 |
| `process_status` | `process_id` | 返回当前 Session 进程的状态、PID、退出码与时间。 |
| `process_logs` | `process_id` | 从开始或 cursor 返回新增日志；可选 `limit` 受本地上限约束。 |
| `process_wait` | `process_id` | 可选 `timeout`，最多等待 `max_bash_timeout_seconds`；返回最新状态。 |
| `process_stop` | `process_id` | 终止当前 Session 所有的目标进程组；幂等。 |

状态为：`starting`、`running`、`exited`、`failed`、`stopped`。未知 ID 或其他 Session 的 ID 统一返回 `PROCESS_NOT_FOUND`，避免通过错误差异探测其他 Session 进程。

## 6. 实施阶段

### 阶段 0：建立 Bash 缺陷基线

**状态：已完成。** 新增 Bash 参数、超时、启动失败、非零退出、输出边界和工具结果契约测试。

**目的**：先将当前不受控行为固化为失败测试，后续每个安全边界都有回归保护。

**改动**：

1. 新增 `tests/tools/test_bash_tool.py`。
2. 编写参数准备失败测试：空命令、非字符串、未知字段、负数/布尔/超限 timeout。
3. 编写 timeout、shell 无法启动、工作目录缺失、非零退出码、编码回退、stdout/stderr 超大输出、输出截断标记测试。
4. 使用模拟进程和临时目录测试；不得启动真实长服务、访问网络或操作用户工作目录。

**主要文件**：

- 新增：`tests/tools/test_bash_tool.py`
- 必要时修改：`tests/test_tool_result_contract.py`

**验收**：

- [ ] 新测试在旧 Bash 上稳定失败。
- [ ] 测试不依赖用户 Shell 配置、网络和真实项目。

### 阶段 1：收紧一次性 Bash 参数与结果契约

**状态：已完成。** Bash 已注册参数解析器，默认 timeout 为 30 秒，最大 timeout 为 600 秒，结果字段固定。

**目的**：让非法命令参数在权限判断前停止，并把前台命令的公开结果稳定下来。

**改动**：

1. 在 `tools/bash.py` 实现 `parse_bash_arguments()` 并注册为 `REGISTER.argument_parser`。
2. 更新 JSON Schema 和 Tool 描述，明确 Bash 只运行有限时长前台命令；删除“不填即无限执行”的描述。
3. 在 `ExecutionContext` 增加命令长度、默认 timeout、最大 timeout 的配置与正值/上下界校验。
4. 统一返回原始 command、shell、cwd、exit_code、timeout 和独立 stdout/stderr 截断标记。
5. 保持非零 exit code 是 `status=ok` 的现有语义，避免把编译失败、测试失败误判为工具基础设施故障。

**主要文件**：

- 修改：`code/agent/tools/bash.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_bash_tool.py`
- 必要时修改：`tests/tools/test_tool_argument_validation.py`

**验收**：

- [ ] 非法参数在权限弹窗前返回 `INVALID_ARGUMENTS`。
- [ ] 未传 timeout 时使用默认值；不能请求无限 timeout 或超过本地最大值。
- [ ] Unix 与 Windows 的公开结果字段一致。

### 阶段 2：安全执行、超时与受限输出

**状态：已完成。** 已使用 `Popen`、独立进程组、并行受限输出读取、进程组终止和最小环境白名单。

**目的**：避免超时遗留子进程，也避免命令输出耗尽桌面应用内存。

**改动**：

1. 用 `subprocess.Popen` 替换 `subprocess.run`，通过独立 Shell 平台适配器启动进程组。
2. 实现受限并发 stdout/stderr 读取器：按块读取、保留头尾、记录总量和截断状态；不完整累积输出。
3. timeout 时终止整个进程组，尽力收集终止前已获得的受限输出，返回 `BASH_TIMEOUT`。
4. 校验 `project_path` 是可进入目录；分别映射 `WORKSPACE_NOT_FOUND`、`BASH_EXECUTABLE_NOT_FOUND`、`BASH_START_FAILED`。
5. 实现平台最小环境构造器，禁止把宿主完整环境变量直接传给命令。
6. 在 `bash` 内部注入执行适配器，测试使用 fake adapter 验证终止、参数和输出边界，不依赖本机 PowerShell/Bash 行为。

**主要文件**：

- 新增：`code/agent/tools/shell_execution.py`
- 修改：`code/agent/tools/bash.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`tests/tools/test_bash_tool.py`

**验收**：

- [ ] stdout/stderr 各自不会超过本地缓冲上限。
- [ ] 超时返回 `BASH_TIMEOUT`，且触发进程组终止。
- [ ] Windows 采用 argv 调用 PowerShell；Unix 采用独立 Bash 进程组。
- [ ] 宿主敏感环境变量不会自动传给子进程。

### 检查点 A：一次性 Bash 安全性

- [x] Bash 参数、权限准备、超时、输出截断和启动失败测试通过。
- [x] 现有权限模式测试及 Tool 结果编码测试通过。
- [x] `pytest -q` 通过后提交“完成 Bash 一次性命令优化”（提交 `18525c6`）。

### 阶段 3：Session Process Manager 基础能力

**状态：已完成。** `SessionExecution` 创建并持有唯一的 `SessionProcessManager`，所有成员 Runtime 共享同一引用；`cancel()` 不清理后台服务，`close()` 调用 `stop_all()`，进程句柄和日志不写入数据库。

**目的**：让持续服务不再阻塞 Runtime，并建立 Session 归属和清理边界。

**改动**：

1. 新增 `session/session_process_manager.py`，定义 `ProcessRecord`、状态机、进程注册表、每流环形日志缓冲、线程安全访问和 ID 生成。
2. 提取阶段 2 Shell 启动/终止适配器，供 Process Manager 复用，禁止复制不同平台的进程控制代码。
3. 为每个 `SessionExecution` 创建一个 `SessionProcessManager`；通过每个成员的 `ExecutionContext` 注入同一引用。
4. 新增 `SessionExecution.close()` 与 `SessionProcessManager.stop_all()`；宿主关闭 Session 或应用退出时调用。`cancel()` 不调用 `stop_all()`。
5. 更新 `SessionService` 的创建、恢复与 Runtime 重建路径，确保同一打开 Session 的成员共享进程管理器；恢复后不恢复旧进程记录。

**主要文件**：

- 新增：`code/agent/session/session_process_manager.py`
- 修改：`code/agent/session/ExecutionContext.py`
- 修改：`code/agent/session/session_service.py`
- 修改：`code/agent/runtime/runtime.py`（如需注销/关闭钩子）
- 新增：`tests/runtime/test_session_process_manager.py`
- 修改：`tests/session/test_session_execution.py`
- 修改：`tests/session/test_session_service.py`

**验收**：

- [ ] 后台进程属于 Session，多 Agent 可共享查看。
- [ ] 取消一轮 Agent 不会停止后台服务；关闭 Session 会停止全部后台进程。
- [ ] 其他 Session 的 manager 无法查询或停止该进程。
- [ ] 应用重建 SessionExecution 后不会对旧 PID 发信号。

### 阶段 4：提供 Process Tool 与日志 cursor

**状态：已完成。** 已提供五个静态 Tool：`process_start`、`process_status`、`process_logs`、`process_wait`、`process_stop`；日志 cursor 绑定 `process_id`，过期时返回 `LOG_CURSOR_EXPIRED`。

**目的**：提供 Agent 可调用、可恢复、不会无限阻塞的后台服务接口。

**改动**：

1. 新增 `tools/process_start.py`、`process_status.py`、`process_logs.py`、`process_wait.py`、`process_stop.py`，分别实现独立的参数解析器和 JSON Schema。
2. 实现 `process_start/process_status/process_logs/process_wait/process_stop`；`process_start` 使用后台模式，不继承 Bash 前台 timeout 语义；`process_wait` 仍必须有限等待。
3. `logs` 使用不透明 cursor，返回新增日志、`next_cursor`、截断和 cursor 过期状态。日志被环形缓冲淘汰后返回 `LOG_CURSOR_EXPIRED`，不静默跳到错误位置。
4. `stop` 对已退出和已停止进程保持幂等，避免 Agent 重试引发错误。
5. 更新 Tool Catalog 和 Agent 工具配置校验，允许 Profile 显式启用所需的 `process_*` 工具。
6. 通过 Tool 结果编码和 Context 持久化路径验证 process 结果可恢复地反馈给模型；不持久化活进程控制句柄。

**主要文件**：

- 新增：`code/agent/tools/process_start.py`
- 新增：`code/agent/tools/process_status.py`
- 新增：`code/agent/tools/process_logs.py`
- 新增：`code/agent/tools/process_wait.py`
- 新增：`code/agent/tools/process_stop.py`
- 修改：`code/agent/tools/catalog.py`（如果辅助模块发现规则需要排除）
- 修改：`code/agent/session/ExecutionContext.py`
- 新增：`tests/tools/test_process_tool.py`
- 修改：`tests/test_tool_catalog.py`
- 必要时修改：`tests/test_tool_result_contract.py`

**验收**：

- [ ] `process_start` 立即返回 `process_id`，不会占用 Agent Loop。
- [ ] `process_logs` 能使用 cursor 无重复续读，且输出受本地上限保护。
- [ ] `process_wait` 有最大 timeout；`process_stop` 终止进程组且幂等。
- [ ] `tail -f` 不再是官方建议的持续日志读取路径。

### 阶段 5：Session 权限与生命周期集成

**状态：已完成。** 已新增 `PROCESS_INSPECT` 与 `PROCESS_STOP` 权限动作；`process_start` 使用 `BASH_EXECUTE`，检查/日志/等待使用 `PROCESS_INSPECT`，停止使用 `PROCESS_STOP`。状态和日志仅能访问当前 Session 内存记录，未知或跨 Session ID 统一返回 `PROCESS_NOT_FOUND`。

**目的**：让持续进程遵从 Session 权限模式，且不扩大其他 Session 的能力范围。

**改动**：

1. 在 `PermissionAction` 增加 `PROCESS_INSPECT`、`PROCESS_STOP`；`process_start` 复用 `BASH_EXECUTE`。
2. 更新 `ModePolicy`：`PROCESS_INSPECT` 与 `PROCESS_STOP` 默认允许，但 manager 必须先验证进程属于当前 Session；`BASH_EXECUTE` 保持 plan deny、build ask、yolo allow。
3. 更新 Runtime 权限事件和前端/CLI 文案：后台启动显示“启动后台进程”，不能伪装为文件目录授权。
4. 更新 `SessionExecution.close()` 的实际调用方；应用退出必须执行统一清理并限制终止等待时间。
5. 保留 `HardSafetyPolicy` 的有限黑名单，但文档明确它不是 Shell 沙箱；不扩展为不可维护的字符串黑名单集合。

**主要文件**：

- 修改：`code/agent/permission/types.py`
- 修改：`code/agent/permission/policies.py`
- 修改：`code/agent/permission/PermissionManager.py`
- 修改：`code/agent/runtime/runtime.py`
- 修改：`code/cli/main.py`
- 需要时修改：Web Session API/关闭生命周期模块
- 修改：`tests/test_permission_policies.py`
- 修改：`tests/test_permission_types.py`
- 修改：`tests/runtime/test_permission_session_isolation.py`

**验收**：

- [ ] plan 不能启动 Bash 或后台进程。
- [ ] build 启动命令时触发 Session 权限请求；session allow/deny 对后续启动生效。
- [ ] status/logs/stop 不能跨 Session 操作，即使调用方获得了其他 Session 的 `process_id`。
- [ ] yolo 仍受绝对硬安全规则约束。

### 检查点 B：持续进程端到端验证

- [ ] 一个 Session 启动开发服务，另一成员读取新日志并停止服务。
- [ ] 取消 Agent 消息后服务仍运行；关闭 Session 后服务和子进程均结束。
- [ ] Windows 与 macOS/Linux 使用同一公开结果契约。
- [ ] `pytest -q`、`python -m compileall -q code/agent` 和 `git diff --check` 通过。

### 阶段 6：文档收口与明确非目标

**状态：已完成。** Tool 描述和计划均明确 Bash 只处理有限前台命令，持续服务使用 `process_*`；没有 OS 级沙箱，当前实现不宣称能够精确限制任意 Shell 命令的文件或网络访问。

**目的**：让模型、用户和后续开发者理解何时使用 Bash、何时使用 Process，避免重新引入无限前台命令。

**改动**：

1. 更新 Bash 和 Process Tool 描述、方法注释与系统提示词（如有工具使用指引），明确前台/后台边界。
2. 在本计划记录最终错误码、默认限制、环境变量策略、Session 生命周期和跨进程限制。
3. 搜索并移除旧描述中的“timeout 不填即无限执行”以及建议 `tail -f` 的文本。
4. 将本计划状态和验收项更新为完成，并记录最终测试结果。

**主要文件**：

- 修改：`code/agent/tools/bash.py`
- 修改：`code/agent/tools/process_start.py`
- 修改：`code/agent/tools/process_status.py`
- 修改：`code/agent/tools/process_logs.py`
- 修改：`code/agent/tools/process_wait.py`
- 修改：`code/agent/tools/process_stop.py`
- 修改：本计划文档
- 必要时修改：`code/agent/runtime/prompt_builder.py`

**验收**：

- [x] Tool Schema、参数解析器、结果结构和描述只表达最终契约。
- [x] 完整测试、编译检查和 `git diff --check` 通过。
- [x] 计划文档准确说明：没有 OS 级沙箱，就不宣称拥有完整 Shell 文件访问控制。

## 7. 测试矩阵

### 7.1 Bash 参数和执行

- 空命令、空白命令、未知字段、非字符串命令。
- `timeout` 缺失、0、负数、布尔值、字符串、超过上限。
- 工作目录为空、删除、无访问权限、不是目录。
- Bash/PowerShell 缺失、启动失败、非零退出、超时。
- UTF-8、带 BOM、系统编码、无法解码输出。
- stdout/stderr 分别超限、同时高输出、截断标记和总量字段。
- 命令环境只包含允许变量，敏感宿主变量不可见。

### 7.2 进程管理

- start 后立即取得 ID；进程立即退出时返回 exited/failed 而不是永久 running。
- 状态转换：starting -> running -> exited / stopped。
- 同 Session 多 Agent 共享进程状态与日志。
- 其他 Session 的 ID 统一 `PROCESS_NOT_FOUND`。
- logs 初次读取、cursor 续读、没有新增、超过返回上限、缓冲淘汰导致 cursor 过期。
- wait 正常退出、有限等待超时、stop 后 wait。
- stop 重试、进程已经退出、进程组包含子进程。
- cancel 不停止；close 和应用 shutdown 执行 stop_all。

### 7.3 权限和安全

- Bash/Process Start 参数解析先于权限请求。
- plan deny、build ask、yolo allow 的 Session 隔离。
- session allow、deny、don't ask 规则只影响本 Session。
- Process Inspect/Stop 不得绕过 Session 所有权检查。
- `rm -rf /` 等现有绝对黑名单仍被拒绝；测试不把有限黑名单误写成完整 Shell 解析承诺。

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| 无 timeout 的前台命令长期占住 Runtime | Agent 无法继续对话 | Bash 始终使用本地默认和最大 timeout；持续任务改用 Process。 |
| 超时后子进程残留 | 端口占用、资源泄露 | 平台进程组/进程树终止，Session close stop_all，自动化测试覆盖。 |
| 大量输出耗尽内存 | 桌面进程不稳定 | 并行、分块、受限缓冲读取；模型输出和日志缓冲均有独立硬上限。 |
| 继承环境泄露凭据 | 命令可读取敏感配置 | 最小环境白名单；敏感变量不自动传递。 |
| 简单 Shell 分析误判访问范围 | 用户以为目录被安全限制 | 首期使用粗粒度执行权限，文档明确限制；未来采用 OS 沙箱。 |
| Windows 子进程终止不完整 | 残留服务/worker | 独立平台适配器和 Windows 进程树终止测试；不能保证时返回受控错误并保留诊断状态。 |
| Process Manager 被错误放进 Agent | 跨 Session 串扰、内存泄露 | 仅由 SessionExecution 持有，并以 Session ID 验证每次操作。 |
| 应用重启后 PID 被重用 | 误杀无关进程 | 进程控制句柄不持久化，恢复 Session 不恢复旧进程记录。 |

## 9. 完成定义

- [x] `bash` 参数在权限检查前严格解析，且永不无限等待。
- [x] Bash stdout/stderr 的内存占用与模型返回内容都有本地硬上限。
- [x] timeout、启动失败、工作目录失效和编码问题均返回稳定错误码。
- [x] 超时和 stop 能处理目标进程组/进程树，而非只终止 Shell 父进程。
- [x] `process_*` 能启动、查询、分页读取日志、有限等待和停止 Session 所属进程。
- [x] 持续服务不会阻塞 Agent Loop，也不会因取消当前消息被误停止。
- [x] Session 关闭时清理后台进程；应用重启不恢复旧 PID。应用宿主若持有 SessionExecution，应在退出时调用 `close()`。
- [x] 权限模式和 Session 授权规则覆盖 Bash/Process Start；状态、日志和停止不能跨 Session。
- [x] `pytest -q`、`python -m compileall -q code/agent` 和 `git diff --check` 通过。

## 10. 实施记录

- `18525c6`：完成 Bash 一次性命令优化。
- `551300f`：新增会话级持续进程管理。
- `06532a3`：提供会话后台进程工具。
- 最终验证：`pytest -q`、`python -m compileall -q code/agent`、`git diff --check`。
