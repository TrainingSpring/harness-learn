# Skills 开发迭代计划（未施工）

> 状态：阶段 0 至阶段 5 已完成；阶段 6 至阶段 7 未施工。
>
> 本文是 Skills 功能的设计与施工计划；各阶段状态以标题和顶部状态为准。
>
> 计划基于当前 `session-6` 分支的实际实现编写。当前数据库 schema 版本为 6，LLM 配置已使用 `protocol` 字段；实施前如果 Agent、Storage 或 Web API 已发生变化，应先重新核对对应文件，不得机械套用本文路径和行号。

## 1. 目标

为项目增加完整的、按 Agent 配置的 Skills 支持。用户可以把符合约定格式的 Skill 放入固定目录，通过设置页刷新或导入到本地 Skill 目录；应用解析后将 Skill 索引保存到当前 workspace 的 SQLite 数据库；创建或编辑 Agent 时可以多选 Skill；Session 创建 Agent 时加载该 Agent 关联的 Skill；运行时根据当前任务按需把 Skill 指令注入模型输入。

最终关系如下：

```text
~/.harness-learn/skills/<skill-name>/SKILL.md
              |
              v
        SkillCatalog 扫描、解析、校验、计算摘要
              |
              v
       SQLite skills / agent_skills
              |
              +--> 设置页 Skills 列表
              |
              +--> Agent 创建/编辑时多选 Skill
              |
              v
        AgentFactory.load()
              |
              v
        Agent.skills = Skills(...)
              |
              v
   PromptBuilder + Runtime 当前轮动态组装模型输入
```

## 2. 非目标

本次计划明确不做以下内容：

1. 不扫描或兼容 `.claude/skills`、`.codex/skills`、`.agents/skills` 等第三方隐藏目录。
2. 不把 Skill 当作 Tool。Skill 不生成 function schema，不直接成为模型可调用函数。
3. 不允许 Skill 绕过现有 Tool、`PermissionManager`、Session 权限模式或工作目录限制。
4. 不允许 Skill 脚本自动安装依赖、读取 API Key、修改权限模式或修改 Session 工作目录。
5. 不把完整 `SKILL.md` 正文永久写入 `Context.messages`，也不把它当作用户或 Agent 历史消息持久化。
6. 不在本阶段实现远程 Skill 市场、Git 仓库同步、自动更新和多用户 Skill 权限隔离。
7. 不在本阶段实现 Skill 内部脚本的独立执行沙箱；脚本若被支持，必须复用现有 shell/process/tool 权限链路。
8. 不通过修改 `Runtime` 的职责来创建另一套 Agent Loop。Runtime 仍然只负责当前 Agent 的循环和模型调用。
9. 不修改当前 Agent 与 Runtime 的已收口职责，不重新引入 `AgentDefinition`、`SessionAgentRuntimeFactory` 或额外的 Runtime 工厂。

## 3. 当前代码基线

当前实现中，以下模块是本计划的直接接入点：

| 现有位置 | 当前职责 | Skills 接入方式 |
| --- | --- | --- |
| `code/agent/runtime/agent.py` | 持有 Agent 身份、Context、Tools、权限、LLM 和 Runtime | 增加运行时 `Skills` 集合，不引入 `AgentProfile` 依赖 |
| `code/agent/runtime/agent_factory.py` | 从 `AgentProfile`、LLM 配置和 ToolCatalog 组装完整 Agent | 新增 Skill 关联加载和 `Skills` 对象组装 |
| `code/agent/runtime/prompt_builder.py` | 将 Agent 字段、工具和 Session 权限组成系统指令 | 增加 Skill 元数据和当前激活 Skill 指令的组装入口 |
| `code/agent/storage/types.py` | 定义 SQLite 对应的持久化领域对象 | 增加 `SkillProfile` 或等价索引对象；`AgentProfile` 增加 Skill 关联字段或由 Repository 聚合返回 |
| `code/agent/storage/migrations.py` | SQLite schema 版本迁移，当前为版本 6 | 增加 `skills` 和 `agent_skills` 表的显式迁移 |
| `code/agent/storage/repositories/agent_profile.py` | 保存和读取 AgentProfile | 保存、读取、校验 Agent 与 Skill 的关联 |
| `code/agent/tools/registry/catalog.py` | 受信任 Tool 元数据目录 | 只作为组织参考，不把 Skill 伪装成 ToolCatalog 项 |
| `client/web/server/app/api/agents.py` | Agent 查询和创建接口 | 接收 `skill_ids`，校验可用 Skill 并返回 Skill 摘要 |
| `client/web/server/app/api/settings.py` | LLM、Tool 设置接口 | 增加 Skill 列表、刷新、导入接口 |
| `client/web/server/app/dependencies.py` | FastAPI 共享服务容器 | 注入 Skill Catalog、Skill Repository、Skill 同步服务 |
| `client/web/front/src/features/agents/components/CreateAgentDialog.tsx` | 创建角色表单 | 增加 Skill 多选区域 |
| `client/web/front/src/features/agents/pages/AgentListPage.tsx` | 加载创建角色所需的 LLM 和 Tool 数据 | 同时读取 Skill 列表并传递给弹窗 |
| `client/web/front/src/features/settings/pages/SettingsLayout.tsx` | 设置页布局 | 保持布局职责，仅增加 Skill 导航入口所需的路由配合 |
| `client/web/front/src/features/settings/pages/ToolSettingsPage.tsx` | Tool 只读设置页 | 不混入 Skill 逻辑；新增独立 `SkillSettingsPage.tsx` |
| `client/web/front/src/api/types.ts` | Web API 类型契约 | 增加 Skill、刷新结果和 Agent Skill 字段 |

当前 Agent 的装配约束必须保留：

```text
SessionService / SessionExecution
    -> 创建 Context、PermissionManager、ExecutionContext
    -> AgentFactory.load()
    -> Agent 自己创建并持有 Runtime
```

Skills 只作为 Agent 的能力指令和资源集合进入上述装配流程；Session 仍然负责上下文，不负责解析 Skill 文件。

## 4. 最终产品形态

### 4.1 用户操作流程

```text
用户把 Skill 放入 ~/.harness-learn/skills/<name>/
        |
        v
设置 -> Skills -> 刷新
        |
        +--> 新目录写入数据库
        +--> 内容摘要变化则更新快照
        +--> 无变化不重复写入
        +--> 缺失或格式错误保留记录并显示状态
        |
        v
新增角色/编辑角色 -> 多选 AVAILABLE Skill
        |
        v
创建 Session -> AgentFactory 根据 AgentProfile 加载 Skill
        |
        v
当前任务需要时，Agent 激活对应 Skill，模型获得 Skill 指令
```

### 4.2 Agent、Skill、Tool 的关系

```text
AgentProfile
├── tools: Tool 名称配置
└── skills: Skill ID 关联

Agent
├── tool_definitions: 可执行工具定义
├── tools: 工具执行入口
├── skills: 已加载的 Skill 集合
├── context: 当前 Session 的上下文
├── permission: 当前 Session 的权限管理器
└── runtime: 当前 Agent 的 Agent Loop
```

两者的边界：

| 项目 | Tool | Skill |
| --- | --- | --- |
| 主要内容 | 可执行函数和参数 schema | 行为指令、知识、参考资料和可选辅助脚本 |
| 模型看到的形式 | function/tool schema | system/developer instructions 或当前任务的指令块 |
| 是否直接执行 | 是 | 否；脚本必须经现有工具链执行 |
| 是否参与权限检查 | Tool 调用直接参与 | Skill 本身不拥有权限，实际操作仍由 Tool/Session 权限决定 |
| 配置位置 | `AgentProfile.tools` | `AgentProfile` 与 `agent_skills` 关联 |
| 生命周期 | 随代码注册 | 随 Skill 目录和数据库索引变化 |

有效能力必须满足：

```text
Skill 声明的 allowed-tools
    ∩ Agent 配置的 tools
    ∩ 当前 Session 可用的权限
```

`allowed-tools` 只是 Skill 对工具的建议或限制，不能扩大 Agent 已配置的工具集合，也不能绕过 Session 权限。

## 5. Skill 文件格式契约

### 5.1 目录结构

只扫描固定目录：

```text
~/.harness-learn/skills/
├── code-review/
│   └── SKILL.md
└── document-processing/
    ├── SKILL.md
    ├── references/
    ├── scripts/
    └── assets/
```

规则：

- Skill 根目录必须是固定目录下的直接子目录。
- 根目录名称使用小写字母、数字和连字符，长度不超过 64 个字符。
- 每个 Skill 根目录必须存在大小写敏感的 `SKILL.md`。
- 不递归把任意嵌套目录识别为 Skill。
- 不扫描项目目录、Workspace 目录或其他隐藏 Skill 目录。
- 同一目录内的 `references/`、`scripts/`、`assets/` 是可选资源目录。
- 资源只能从 Skill 根目录内解析，禁止通过 `..` 或符号链接逃逸。

### 5.2 `SKILL.md` frontmatter

至少支持以下格式：

```yaml
---
name: code-review
description: Review code changes for bugs, security issues, regressions, and missing tests.
license: MIT
compatibility: Requires git and Python
metadata:
  author: example
allowed-tools: Read Bash
---

# Code Review

正文是 Skill 指令。
```

字段定义：

| 字段 | 类型 | 必填 | 备注 |
| --- | --- | --- | --- |
| `name` | 字符串 | 是 | Skill 的规范名称；用于选择、展示和匹配。应与目录名一致或至少经过明确校验；不一致时以文件字段为规范值并报告警告，不能静默改名 |
| `description` | 字符串 | 是 | 用于 Skill 选择和设置页展示的简短描述；不能把完整指令塞进描述 |
| `license` | 字符串 | 否 | 许可证或授权说明，仅保存和展示，不由运行时解释 |
| `compatibility` | 字符串 | 否 | 对运行环境、依赖或平台的说明，仅保存和展示，不自动安装依赖 |
| `metadata` | mapping | 否 | 未标准化扩展元数据；保留为 JSON，不参与核心路由逻辑 |
| `allowed-tools` | 字符串或字符串列表 | 否 | Skill 建议或限制使用的工具名；必须与 Agent 已配置工具求交集，不能授权新工具 |
| Markdown 正文 | 文本 | 是 | Skill 的实际行为指令；按 UTF-8 读取，保留原始 Markdown 语义 |

解析规则：

1. frontmatter 必须位于文件开头，以 `---` 成对包围。
2. `name` 和 `description` 缺失、为空或类型错误时，记录为 `INVALID`。
3. 未知 frontmatter 字段允许保留，但当前运行时忽略，避免破坏主流 Skill。
4. YAML 解析失败时，不能让一次刷新中断其他 Skill 的同步；只把当前 Skill 标记为 `INVALID` 并保存错误原因。
5. frontmatter 中不得执行表达式、导入模块或展开外部文件。
6. 正文为空可以根据产品决定是否允许；建议允许解析但在 UI 标记警告，避免因为空正文阻止索引其他字段。
7. 解析器只负责格式和字段，不负责判断 Skill 是否适合当前任务。

### 5.3 资源目录

| 目录 | 作用 | 第一版规则 |
| --- | --- | --- |
| `references/` | 按需读取的参考资料 | 只允许读取 Skill 根目录内文件，读取结果受内部大小限制 |
| `scripts/` | 可选辅助脚本 | 不自动执行；若未来执行，必须进入现有 Bash/Process/Permission 流程 |
| `assets/` | 生成结果或工作流需要的静态资源 | 只作为受控资源读取，不作为指令执行 |
| `agents/` | 第三方 Skill 的 UI 元数据或调用策略 | 本项目第一版不依赖、不要求、不执行 |

## 6. Python 模块设计

建议新增目录：

```text
code/agent/skills/
├── __init__.py
├── types.py
├── parser.py
├── catalog.py
├── skills.py
└── resources.py
```

### 6.1 `code/agent/skills/types.py`（新增）

定义 Skill 领域对象和状态，不执行文件扫描或数据库操作。

建议类型：

```python
class SkillStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    INVALID = "INVALID"
    MISSING = "MISSING"

@dataclass(frozen=True)
class SkillDefinition:
    id: str
    name: str
    description: str
    root_path: str
    instructions: str
    license: str | None
    compatibility: str | None
    metadata: dict[str, Any]
    allowed_tools: tuple[str, ...]
    content_digest: str
    status: SkillStatus
    validation_error: str | None
```

属性备注：

| 属性 | 说明 |
| --- | --- |
| `id` | 稳定 Skill ID，建议使用 `skill_` 前缀；与目录名和显示名称解耦，避免目录改名破坏 Agent 关联 |
| `name` | `SKILL.md` frontmatter 中的规范名称，展示和模型 Skill 元数据使用该字段 |
| `description` | Skill 选择阶段可见的短描述，不包含完整正文 |
| `root_path` | 固定 Skill 根目录的规范化绝对路径；不能接受任意用户提交的外部路径 |
| `instructions` | `SKILL.md` 正文快照；只在需要时加载到运行时，不直接进入 Context 历史 |
| `license` | 可选许可证文本 |
| `compatibility` | 可选环境兼容说明 |
| `metadata` | 未标准化 frontmatter 字段，保留为字典 |
| `allowed_tools` | 解析后的工具名元组；只表示限制/建议，不能绕过 Agent 和 Session 能力 |
| `content_digest` | Skill 目录内容的 SHA-256 摘要，用于刷新时判断真实内容是否变化 |
| `status` | 当前索引状态：可用、格式无效或目录缺失 |
| `validation_error` | 解析或校验失败的稳定错误摘要；可供设置页展示，禁止泄漏堆栈和敏感路径 |

该对象应避免保存数据库连接、文件句柄或 Agent/Runtime 引用。

### 6.2 `code/agent/skills/parser.py`（新增）

负责解析单个 `SKILL.md`：

- 拆分 YAML frontmatter 和 Markdown 正文。
- 解析标准字段和未知字段。
- 校验字段类型、长度、必填项和命名规则。
- 规范化 `allowed-tools` 的字符串/列表两种输入。
- 返回可用于落库的解析结果或结构化校验错误。
- 禁止执行正文、frontmatter 或脚本。

建议暴露小接口：

```python
parse_skill_file(path: Path) -> ParsedSkill
```

解析器使用 YAML 解析库时应锁定安全加载模式；不得使用可执行对象构造器。

### 6.3 `code/agent/skills/catalog.py`（新增）

负责固定目录的发现、目录摘要和单次同步前的文件系统读取。

建议职责：

- 计算 `~/.harness-learn/skills` 的规范根路径。
- 只发现直接子目录。
- 检查 `SKILL.md` 是否存在且为普通文件。
- 校验符号链接和资源路径不能逃逸 Skill 根目录。
- 计算整个 Skill 目录的确定性 SHA-256 摘要。
- 读取目录内容后委托 `parser.py` 解析。
- 返回发现结果，不直接写 SQLite。

建议接口：

```python
list_discovered() -> list[DiscoveredSkill]
load(skill_id_or_name: str) -> SkillDefinition
digest(root: Path) -> str
```

目录摘要必须包含相对路径、文件类型、文件内容和稳定排序，不能只依赖目录修改时间；这样能识别内容被修改但 mtime 不可靠的情况。

### 6.4 `code/agent/skills/skills.py`（新增）

定义 Agent 运行时使用的已分配 Skill 集合，不负责扫描目录和数据库同步。

建议职责：

- 按 Agent 配置的稳定顺序保存 `SkillDefinition`。
- 提供名称/ID 查询。
- 输出轻量 Skill 元数据给 PromptBuilder。
- 根据当前任务选择要激活的 Skill。
- 在激活时读取正文，或返回受控的指令块。
- 过滤 `allowed_tools` 与 Agent 当前 Tool 集合的交集。

建议接口：

```python
list_metadata() -> tuple[SkillMetadata, ...]
activate(skill_id: str) -> SkillInstructions
activate_for_task(selection: Iterable[str]) -> tuple[SkillInstructions, ...]
```

第一版可以由 Runtime/PromptBuilder 接收当前激活 Skill 名称；不能在 `Skills` 内部自行调用 LLM 判断任务，也不能把每个 Skill 的全部正文固定拼入所有轮次。

### 6.5 `code/agent/skills/resources.py`（新增）

集中处理 Skill 资源路径和资源读取：

- 将用户提供的相对资源路径解析为 Skill 根目录内的路径。
- 拒绝绝对路径、`..` 路径、符号链接逃逸和目录穿越。
- 限制单文件字节数、总读取字节数和结果长度。
- 区分参考资料读取和脚本执行；本模块不执行脚本。
- 为未来的 Skill 资源 Tool 提供可测试的深模块接口。

## 7. Storage 设计

### 7.1 `code/agent/storage/types.py`（修改）

新增 `SkillProfile`（名称可按项目已有术语调整）并在 `AgentProfile` 中体现 Skill 关联。

推荐的领域对象：

```python
@dataclass
class SkillProfile:
    id: str
    name: str
    description: str
    root_path: str
    instructions: str
    license: str | None
    compatibility: str | None
    metadata: dict[str, Any]
    allowed_tools: list[str]
    content_digest: str
    status: str
    validation_error: str | None
    discovered_at: str | None = None
    updated_at: str | None = None
```

属性备注：

| 属性 | 备注 |
| --- | --- |
| `id` | 数据库稳定主键，删除或目录重新发现时不依赖展示名称 |
| `name` | Skill 规范名称，建议唯一；同名导入时必须显式提示覆盖/取消 |
| `description` | 设置页、角色配置页和运行时元数据展示文本 |
| `root_path` | 本机 Skill 根目录规范路径，只接受 `~/.harness-learn/skills` 下的目录 |
| `instructions` | `SKILL.md` 正文快照；用于数据库可读和运行时加载，内容变化时随 digest 更新 |
| `license` | frontmatter 的许可证原文 |
| `compatibility` | frontmatter 的兼容性说明 |
| `metadata` | 未标准化字段的 JSON 保存值 |
| `allowed_tools` | frontmatter 的工具限制/建议的 JSON 数组 |
| `content_digest` | 目录完整内容摘要，刷新判定的唯一依据 |
| `status` | `AVAILABLE`、`INVALID` 或 `MISSING` |
| `validation_error` | 当前错误原因；成功恢复后清空 |
| `discovered_at` | 首次被刷新发现的时间 |
| `updated_at` | Skill 索引快照实际变化的时间；无变化刷新不得更新 |

`AgentProfile` 不应直接保存完整 `SkillProfile` 对象。建议在领域层增加：

```python
skills: list[str]
```

该字段只表示关联的 Skill ID 顺序；完整 Skill 数据由 SkillRepository 按 ID 查询。

### 7.2 `code/agent/storage/migrations.py`（修改）

将 `CURRENT_SCHEMA_VERSION` 从 6 提升到下一版本，并增加显式迁移函数 `_migrate_version_six_to_seven()`。

建议新增表：

```sql
CREATE TABLE skills (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL,
    root_path TEXT NOT NULL UNIQUE,
    instructions TEXT NOT NULL DEFAULT '',
    license TEXT,
    compatibility TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    allowed_tools_json TEXT NOT NULL DEFAULT '[]',
    content_digest TEXT NOT NULL,
    status TEXT NOT NULL,
    validation_error TEXT,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE agent_skills (
    agent_id TEXT NOT NULL,
    skill_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (agent_id, skill_id),
    FOREIGN KEY (agent_id) REFERENCES agent_profiles(id) ON DELETE CASCADE,
    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE RESTRICT
);

CREATE INDEX idx_agent_skills_agent_position
    ON agent_skills(agent_id, position);
```

表字段备注：

#### `skills`

| 字段 | 备注 |
| --- | --- |
| `id` | 稳定 Skill ID，外键关联 Agent；不能用名称替代主键 |
| `name` | Skill 规范名称，唯一，供 UI 展示和运行时选择 |
| `description` | 可选 Skill 的短描述，必填以便 UI 选择 |
| `root_path` | 固定 Skill 根目录的规范绝对路径，唯一 |
| `instructions` | `SKILL.md` 正文快照，不保存 frontmatter 原文 |
| `license` | 可空许可证字段 |
| `compatibility` | 可空兼容性字段 |
| `metadata_json` | 未标准化 frontmatter 的 JSON 对象 |
| `allowed_tools_json` | 工具名数组 JSON |
| `content_digest` | 目录内容 SHA-256，刷新比较字段 |
| `status` | 只允许 `AVAILABLE`、`INVALID`、`MISSING` |
| `validation_error` | 格式或文件错误，正常时为 NULL |
| `discovered_at` | 首次发现时间 |
| `updated_at` | 索引快照最后变化时间 |

#### `agent_skills`

| 字段 | 备注 |
| --- | --- |
| `agent_id` | `agent_profiles.id` 外键 |
| `skill_id` | `skills.id` 外键 |
| `position` | Agent 内 Skill 的稳定展示和加载顺序，从 0 或 1 开始但必须统一 |
| `created_at` | 关联创建时间 |

推荐独立 `agent_skills` 表，而不是向 `agent_profiles` 增加 `skills_json`，原因：

- Skill 有自己的状态、摘要、错误和目录生命周期。
- 可以查询 Skill 被多少个 Agent 使用。
- 可以保持 Agent 的关联顺序并对重复关联施加数据库约束。
- 未来可以为 Skill 增加版本、来源或更新时间，而不让 AgentProfile 继续膨胀。
- 删除 Agent 时可以级联删除关联，删除 Skill 时通过 `RESTRICT` 防止静默破坏角色配置。

迁移要求：

- 迁移必须显式、可重复执行且不能依赖“表是否存在”猜版本。
- 旧 Agent 没有 Skill 时迁移后关联为空，不能影响现有会话。
- 不修改或覆盖 `.harness/state.db` 中用户已有数据；测试迁移使用临时数据库。
- 迁移失败要回滚，数据库版本不能写成新版本。

### 7.3 新增 Repository

新增：

```text
code/agent/storage/repositories/skill.py
```

职责：

- `get(skill_id)`、`get_by_name(name)`。
- `list_all()`，支持状态筛选和稳定排序。
- `list_for_agent(agent_id)`，按 `position` 返回关联 Skill。
- `upsert(skill)`，按 ID/名称更新 Skill 索引快照。
- `replace_agent_skills(agent_id, skill_ids)`，在一个事务内替换关联顺序。
- `count_agents(skill_id)`，供设置页展示使用角色数。
- `mark_missing(path/digest scope)`，刷新时将未发现的已知目录标记为缺失。

Repository 只处理 SQL 和领域对象转换，不扫描文件、不解析 YAML、不创建 Agent、不决定 Skill 是否激活。

## 8. 同步和导入机制

### 8.1 刷新语义

设置页的刷新操作调用同步服务，不能由 React 页面直接读文件系统。

每次刷新：

1. 扫描固定目录的直接子目录。
2. 为每个发现的 Skill 计算完整目录 digest。
3. digest 不存在：新增数据库记录，状态为 `AVAILABLE` 或 `INVALID`。
4. digest 与数据库相同：不更新正文、时间戳或关联。
5. digest 变化：重新解析并更新索引快照；解析失败时状态变为 `INVALID`，保留错误原因。
6. 数据库已有、文件系统本次未发现：标记为 `MISSING`，不直接删除。
7. 已经 `MISSING` 的 Skill 重新出现且解析成功：恢复为 `AVAILABLE`。
8. 已经关联到 Agent 的 `MISSING` Skill 不自动从 Agent 关联中删除，以便用户修复目录后恢复；创建新 Agent 时不可选择 `MISSING`。

刷新结果必须返回摘要：

```text
新增 N
更新 N
未变化 N
缺失 N
无效 N
```

不能只比较 mtime，因为文件复制、时钟变化或外部工具可能导致 mtime 不可靠。

### 8.2 `code/agent/skills/sync_service.py`（新增）

建议新增同步服务，负责协调 `SkillCatalog`、`SkillParser` 和 `SkillRepository`：

- 在一个明确的同步操作中计算结果。
- 单个 Skill 失败不影响其他 Skill。
- 数据库写入按 Skill 事务化；不要让半个 Skill 快照成功。
- 返回结构化 `SkillSyncResult`，供 API 和测试使用。
- 对错误分类：目录缺失、权限错误、frontmatter 错误、编码错误、摘要错误。

该服务属于应用/领域协调层，不放进 `StateDatabase`，也不让 `SkillCatalog` 直接持久化。

### 8.3 “新增 Skill”定义

设置页的“新增 Skill”不创建空 Skill 记录，而是执行导入：

1. 用户选择一个 Skill 目录或 zip 文件。
2. 服务端校验入口存在 `SKILL.md`。
3. 解析并校验 Skill 名称、目录名和资源路径。
4. 复制到 `~/.harness-learn/skills/<skill-name>/`。
5. 若同名或目标目录已存在，明确提示覆盖、取消或另存，不静默合并。
6. zip 解压前检查路径穿越、绝对路径和符号链接逃逸。
7. 导入完成后执行一次同步并返回 Skill 详情。

导入接口不能接受任意服务器路径作为最终 Skill 根目录；文件选择器传递的路径也必须经过服务端规范化和固定根目录校验。

## 9. Agent 运行时改造

### 9.1 `code/agent/runtime/agent.py`（修改）

新增构造参数和属性：

```python
skills: Skills
```

属性备注：

- `skills` 是当前 Agent 已分配的运行时 Skill 集合。
- 它不等同于数据库 `SkillProfile` 列表，数据库对象不能泄漏到 Runtime 核心。
- 它与 `context` 同属当前 Session 的运行时依赖，但不负责上下文持久化。
- 它不能修改 Session 权限，也不能自行注册 Tool。

`Agent.run()` 仍然调用内部 Runtime；如果需要动态 Skill 指令，Agent 应向 Runtime/PromptBuilder 提供当前激活 Skill 指令，而不是让 Session 直接操作 Runtime 内部状态。

### 9.2 `code/agent/runtime/agent_factory.py`（修改）

新增 `SkillRepository` 或 `SkillLoader` 依赖，并在 `load()` 中：

1. 读取 AgentProfile 的 Skill ID 顺序。
2. 查询对应 Skill 索引。
3. 对不存在的 Skill 返回配置错误或明确的降级结果，不能静默加载错误角色。
4. `MISSING`、`INVALID` Skill 的处理策略要固定：建议允许已有 Agent 加载但把状态暴露给 UI/运行时并跳过不可用指令；是否允许 Session 启动必须在实现阶段按产品最终确认。
5. 创建 `Skills` 运行时对象。
6. 将 `Skills` 传给 `Agent`。

Factory 仍然是 storage 到运行时的装配点；Session 不直接读取 Skill 表，也不直接实例化 `Skills` 内部组件。

### 9.3 `code/agent/runtime/prompt_builder.py`（修改）

PromptBuilder 应服务于运行时 `Agent` 和 `Skills`，不服务于 `AgentProfile`。

建议把 Prompt 分成三层：

1. Agent 基础指令：名称、描述、性格、专长、权限模式和工具。
2. Skill 元数据：名称和描述，帮助模型知道当前 Agent 可用哪些 Skill。
3. 当前激活 Skill 指令：只注入本轮任务实际需要的 Skill 正文或指令块。

必须解决“动态指令”的问题：当前 `LLM` 在 Agent 初始化时接收固定 `instructions`，完整 Skill 支持不能简单把所有 Skill 正文永久拼进去。实施时需要二选一并写测试：

- 方案 A：扩展 LLM/Runtime 的单轮调用接口，允许每轮传递动态 instruction blocks。
- 方案 B：保留基础 system prompt，Runtime 在模型输入组装阶段增加当前轮临时 system/developer 消息。

推荐方案 A 或等价的“每轮动态指令”接口，因为 Skill 激活集合可能按任务变化，且不应污染 Context 历史。无论采用哪种实现，都必须满足：

- Skill 指令不会作为用户消息写入 Context。
- 下一轮未激活的 Skill 不会继续残留。
- Context 恢复时不需要重新追加重复的 Skill 历史消息。
- 基础 Agent Prompt 和 Session 权限规则继续稳定存在。

### 9.4 `code/agent/runtime/runtime.py`（谨慎修改）

只有在动态模型输入确实需要时才修改 Runtime。Runtime 的职责仍是：

- 负责 Agent Loop。
- 根据 Agent/Context 生成当前模型输入。
- 执行模型调用和 Tool 调用。
- 传播权限请求、工具事件和运行事件。

Runtime 不负责：

- 扫描 Skill 目录。
- 写 Skill 数据库。
- 修改 AgentProfile。
- 决定目录刷新或导入。

本计划明确不通过增加 `next()`、新的 Runtime 工厂或第二套 Loop 来实现 Skills。

## 10. Web 后端 API

### 10.1 `client/web/server/app/schemas/settings.py`（修改）

新增 DTO：

```python
class SkillSummary(ApiModel):
    id: str
    name: str
    description: str
    license: str | None
    compatibility: str | None
    status: Literal["AVAILABLE", "INVALID", "MISSING"]
    validation_error: str | None
    agent_count: int
    updated_at: str

class SkillSyncResult(ApiModel):
    added: int
    updated: int
    unchanged: int
    missing: int
    invalid: int
    items: list[SkillSummary]
```

必要时增加 `SkillDetail`，但默认列表不返回完整 `instructions`，避免设置页一次加载大量内容。

### 10.2 `client/web/server/app/schemas/agent.py`（修改）

修改 `AgentSummary`、`AgentDetail` 和 `CreateAgentRequest`：

```python
class AgentSummary(ApiModel):
    ...
    skills: list[str]

class CreateAgentRequest(ApiModel):
    ...
    skill_ids: list[str] = Field(default_factory=list)
```

属性备注：

- `skills` 是返回给 Web 的 Skill 摘要名称或 ID 列表，建议返回 ID 与名称的结构对象以避免前端二次查询。
- `skill_ids` 是用户提交的 Skill 稳定 ID，不能提交名称代替，也不能提交完整 Skill 内容。
- 服务端必须去重并保留用户选择顺序。
- 只允许关联 `AVAILABLE` Skill；编辑旧 Agent 时可以回显 `MISSING`/`INVALID`，但新增关联不能选择它们。

### 10.3 `client/web/server/app/api/settings.py`（修改）

新增路由建议：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| `GET` | `/api/settings/skills` | 从数据库分页/读取 Skill 索引列表 |
| `POST` | `/api/settings/skills/refresh` | 扫描固定目录并同步数据库，返回刷新摘要 |
| `POST` | `/api/settings/skills/import` | 导入目录或 zip 到固定 Skill 目录后同步 |
| `GET` | `/api/settings/skills/{skill_id}` | 查看单个 Skill 元数据和受控详情 |

API 注意事项：

- `GET /skills` 不扫描文件系统，数据库是设置页和 Agent 表单的读取源。
- `POST /refresh` 需要幂等；重复刷新无变化时不能制造更新时间变化。
- 错误响应使用已有 `ApiError` 体系，不把 Python 堆栈、绝对本地路径或密钥返回给浏览器。
- 刷新期间的单个 Skill 错误作为结果状态返回，不应让整个请求因为一个坏 Skill 变成 500。
- 导入接口必须限制上传大小和解压后总大小，避免压缩炸弹。

### 10.4 `client/web/server/app/api/agents.py`（修改）

创建和读取 Agent 时：

1. 注入 Skill Repository/Service。
2. 校验提交的 `skill_ids` 都存在且状态为 `AVAILABLE`。
3. 创建 AgentProfile 和 `agent_skills` 关联必须是一个事务语义；Agent 保存成功但关联失败不能返回半成功。
4. 返回 Agent 详情时带 Skill 摘要。
5. 如果已有编辑接口，编辑时使用 replace 语义维护关联顺序；如果当前只有创建接口，计划中补充详情编辑接口的扩展点，但不为本阶段无关功能新增整套编辑页面。

### 10.5 `client/web/server/app/dependencies.py`（修改）

`ApplicationServices` 增加：

- `skill_catalog`
- `skill_profiles` 或 `skill_repository`
- `skill_sync_service`

服务容器注释必须说明：

- Catalog 负责文件系统发现和解析。
- Repository 负责数据库索引。
- Sync service 负责二者协调。
- AgentFactory 使用 Repository/Loader 读取已同步 Skill，不在 Session 请求中扫描目录。

## 11. Web 前端改造

### 11.1 `client/web/front/src/api/types.ts`（修改）

新增：

```typescript
export type SkillStatus = "AVAILABLE" | "INVALID" | "MISSING";

export interface SkillSummary {
  id: string;
  name: string;
  description: string;
  license: string | null;
  compatibility: string | null;
  status: SkillStatus;
  validationError: string | null;
  agentCount: number;
  updatedAt: string;
}

export interface SkillSyncResult {
  added: number;
  updated: number;
  unchanged: number;
  missing: number;
  invalid: number;
  items: SkillSummary[];
}
```

扩展 `AgentSummary`、`AgentDetail`、`CreateAgentRequest` 的 Skill 字段，并与后端 camelCase 转换规则保持一致。

### 11.2 `client/web/front/src/features/settings/api.ts`（修改）

新增函数：

- `listSkills()`：读取数据库 Skill 列表。
- `refreshSkills()`：触发服务器同步。
- `importSkill()`：提交目录/zip 导入请求，具体上传方式按现有 `apiClient` 能力决定。
- `getSkill(skillId)`：读取详情。

### 11.3 新增设置页

新增：

```text
client/web/front/src/features/settings/pages/SkillSettingsPage.tsx
client/web/front/src/features/settings/components/SkillList.tsx（可选）
client/web/front/src/features/settings/components/SkillRow.tsx（可选）
```

页面要求：

- 设置页导航增加“Skills”。
- 右上角提供“新增 Skill”和刷新图标按钮。
- 列表显示名称、描述、状态、使用角色数和更新时间。
- `AVAILABLE`、`INVALID`、`MISSING` 使用不同的可理解状态展示。
- 刷新完成后显示新增、更新、未变化、缺失和无效摘要。
- 允许查看错误原因，但不显示服务器绝对路径或堆栈。
- 列表读取数据库，不在组件中扫描目录。
- 刷新按钮要有 pending、成功、失败和重复点击禁用状态。

### 11.4 `SettingsNav.tsx`、路由和样式（修改）

- `client/web/front/src/features/settings/components/SettingsNav.tsx` 增加 Skills 导航项和合适的 Lucide 图标。
- `client/web/front/src/app/router.tsx` 增加 `SkillSettingsPage` lazy route，例如 `/settings/skills`。
- 复用现有设置页布局和列表样式，不将 Skill 页面嵌套在 Tool 卡片中。
- 若新增导入弹窗，使用现有 Dialog/Focus/错误反馈约定，并覆盖键盘操作、空列表和加载状态。

### 11.5 `CreateAgentDialog.tsx` 和 `AgentListPage.tsx`（修改）

角色弹窗在“可用工具”下面增加“Skills”多选区域：

```text
可用工具
☑ read
☑ write
☐ bash

Skills
☑ code-review
☐ document-processing
```

交互要求：

- 只展示数据库中的 `AVAILABLE` Skill。
- 没有 Skill 时显示明确空状态，不阻止创建 Agent。
- 编辑已有 Agent 时，已关联但当前 `MISSING`/`INVALID` 的 Skill 继续回显并显示警告，不能被静默丢掉。
- Skill 多选顺序稳定，提交 `skillIds` 数组。
- 创建成功后 Agent 列表和 Skill 使用计数刷新。
- `AgentListPage` 同时加载 `listSkills()`，但不触发 refresh。
- Skill 查询失败不能把 LLM 或 Tool 查询错误伪装成 Agent 创建失败；表单需要显示独立错误状态。

## 12. 运行时 Skill 注入方案

### 12.1 三阶段信息披露

采用渐进式加载：

1. **选择阶段**：模型只获得 Skill `name + description` 元数据，或由 PromptBuilder 生成简短可用列表。
2. **激活阶段**：当前任务需要某 Skill 时，加载该 Skill 的 Markdown 正文作为临时指令块。
3. **资源阶段**：只有当前任务需要时，读取 `references/` 或通过受控 Tool 使用其他资源。

不把所有 Skill 正文永久放进每轮 system prompt，原因：

- Agent 可能关联很多 Skill，会浪费 Token。
- Skill 正文不是会话历史，不应被压缩和恢复逻辑当作历史消息。
- 一个 Session 的任务可能只需要少数 Skill。
- 动态激活能够降低模型被无关 Skill 干扰的风险。

### 12.2 激活来源

第一版必须明确激活来源，避免“模型自由拼字符串”造成不可控行为。推荐顺序：

1. Agent 配置提供可用 Skill 集合。
2. Runtime/PromptBuilder 接收当前轮由上层确定的激活 Skill ID。
3. `Skills` 校验激活 Skill 必须属于 Agent 已分配集合且状态可用。
4. 生成临时 instructions，随当前模型输入发送。

如果第一版暂时没有独立 Skill 选择 Tool，可以先把所有已分配 Skill 的 `name + description` 注入基础 Prompt，并只在明确的运行时参数中激活正文；不要让任意模型输出直接读取任意磁盘路径。

### 12.3 Context 边界

Skill 正文、frontmatter 和资源内容的规则：

- 不写入 `Context.append()` 的用户消息或 Agent 消息。
- 不生成 `ContextItem`，除非未来明确要记录“使用了哪个 Skill”的审计事件；即使记录，也只记录 Skill ID 和版本摘要，不记录整篇正文。
- 运行时重新恢复 Session 后，按照 Agent 配置重新加载 Skill 集合即可。
- Context 压缩不负责压缩 Skill 指令。
- Skill 资源读取结果如果影响模型回答，实际结果可以作为当前工具输出进入 Context，但必须受现有输出截断策略限制。

## 13. 权限和安全

### 13.1 工具能力求交集

Skill 的 `allowed-tools` 不能授予能力。实际可调用工具必须是：

```text
Skill allowed-tools（未声明时表示不额外限制，仍受 Agent tools 限制）
    ∩ AgentProfile.tools
    ∩ ToolCatalog 已注册工具
    ∩ Session 权限模式和用户确认结果
```

具体实现要区分“Skill 未声明 allowed-tools”和“Skill 明确声明空列表”：

- 未声明：不增加额外限制，仍只能使用 Agent 已配置工具。
- 已声明：只允许交集中的工具。
- 声明不存在的工具：记录警告，不自动注册或加载。

### 13.2 文件和资源安全

- Skill 根目录必须在 `~/.harness-learn/skills` 下。
- 资源解析后必须 `resolve()` 并验证仍位于 Skill 根目录内。
- 拒绝 `../secret`、绝对路径、UNC 路径和符号链接逃逸。
- `SKILL.md`、参考文件和脚本读取设置字节上限。
- zip 导入检查每个成员路径和解压总大小。
- 不执行 frontmatter、Markdown 中的代码块或 scripts 目录脚本。
- Skill 文本不能读取环境变量、API Key 或数据库凭据。
- 所有真正的文件写入、Shell 执行和进程操作仍由现有 Tool 和 PermissionManager 处理。

### 13.3 状态和错误安全

- `INVALID` Skill 不得注入正文。
- `MISSING` Skill 不得根据旧快照继续读取磁盘内容。
- 解析异常对用户返回稳定错误摘要，不返回内部堆栈。
- Agent 启动时发现关联 Skill 不可用，必须有确定策略：建议保留 Agent 并跳过不可用 Skill，同时发送可诊断的运行事件；若产品要求严格，则在创建 Agent 时阻止关联并在旧配置上显示修复提示。
- UI 不显示 API Key、完整绝对路径或内部 SQL 错误。

## 14. 分阶段施工计划

每个任务都需要在本阶段完成对应测试；未满足验收标准不得进入下一阶段。

### 阶段 0：契约和测试夹具（已完成）

**目标**：先固定 Skill 格式、状态、同步语义和运行时边界。

**新增/修改**：

- 新增 `docs/plan/Skills开发迭代计划（未施工）.md`（本文）。
- 新增测试夹具目录，例如 `tests/fixtures/skills/`，包含有效、无 frontmatter、YAML 错误、缺字段、未知字段、资源目录和路径穿越样例。
- 新增 `tests/skills/` 测试目录。

**验收**：

- 能用测试样例明确区分 `AVAILABLE`、`INVALID`、`MISSING`。
- 能明确验证 Skill 不等于 Tool，不直接写入 Context。

### 阶段 1：Skill 类型、解析器和目录 Catalog（已完成）

**目标**：不接数据库，先实现可独立测试的 Skill 发现和解析。

**新增**：

- `code/agent/skills/__init__.py`
- `code/agent/skills/types.py`
- `code/agent/skills/parser.py`
- `code/agent/skills/catalog.py`
- `code/agent/skills/resources.py`
- 对应单元测试。

**验收**：

- 只扫描 `~/.harness-learn/skills` 的直接子目录。
- 正确解析标准 frontmatter 和 Markdown 正文。
- 保留未知字段，不执行未知字段内容。
- 能识别目录缺失、`SKILL.md` 缺失、编码错误、YAML 错误和字段类型错误。
- 目录摘要对内容修改敏感，对稳定排序不敏感。
- 所有资源路径穿越和符号链接逃逸测试通过。

### 阶段 2：数据库表和 Repository（已完成）

**目标**：保存 Skill 索引快照和 Agent-Skill 关联。

**修改**：

- `code/agent/storage/migrations.py`
- `code/agent/storage/types.py`
- `code/agent/storage/repositories/__init__.py`
- `code/agent/storage/repositories/agent_profile.py`

**新增**：

- `code/agent/storage/repositories/skill.py`
- `tests/storage/test_skill_repository.py`
- `tests/storage/test_skill_migrations.py`

**验收**：

- 旧版本数据库能升级到新版本。
- 新数据库能直接创建 Skill 表和关联表。
- Skill 的 JSON 字段读写严格校验。
- `agent_skills` 保留 position，重复关联被拒绝或幂等处理。
- 删除 Agent 级联删除关联；删除被 Agent 使用的 Skill 被阻止。
- MISSING/INVALID 记录可持久化，修复后可恢复 AVAILABLE。

### 阶段 3：同步服务和固定目录刷新（已完成）

**目标**：把文件系统发现结果同步为数据库索引。

**新增**：

- `code/agent/skills/sync_service.py`
- `tests/skills/test_skill_sync_service.py`

**修改**：

- 应用服务装配入口，例如 `client/web/server/app/bootstrap.py` 或当前实际初始化服务的文件。
- `client/web/server/app/dependencies.py`。

**验收**：

- 新增、更新、未变化、缺失、无效五类统计准确。
- 同一内容重复刷新不修改 `updated_at`。
- 单个坏 Skill 不影响其他 Skill 刷新。
- 文件删除后记录变为 MISSING，不直接删除。
- 目录恢复后记录恢复 AVAILABLE。
- 不扫描第三方隐藏 Skill 目录。

### 阶段 4：设置页 API 和 Skill 管理 UI

**目标**：用户可以查看、刷新和导入 Skill。

**后端修改**：

- `client/web/server/app/schemas/settings.py`
- `client/web/server/app/api/settings.py`
- `client/web/server/app/dependencies.py`

**前端修改**：

- `client/web/front/src/api/types.ts`
- `client/web/front/src/features/settings/api.ts`
- `client/web/front/src/features/settings/components/SettingsNav.tsx`
- `client/web/front/src/app/router.tsx`

**前端新增**：

- `client/web/front/src/features/settings/pages/SkillSettingsPage.tsx`
- 必要的 Skill 行、状态和导入组件。

**验收**：

- 设置页列表只读数据库索引。
- 刷新按钮能调用后端并显示同步摘要。
- 新增 Skill 能完成目录/zip 导入和校验。
- 无 Skill、加载中、刷新中、错误、无效和缺失状态都可理解且不重叠。
- 同名导入有明确的覆盖/取消结果。

### 阶段 5：Agent 配置和 Factory 装配（已完成）

**目标**：Skill 可以按 Agent 保存和加载。

**修改**：

- `code/agent/storage/types.py`
- `code/agent/storage/repositories/agent_profile.py`
- `code/agent/runtime/agent_factory.py`
- `code/agent/runtime/agent.py`
- `client/web/server/app/schemas/agent.py`
- `client/web/server/app/api/agents.py`
- `client/web/front/src/api/types.ts`
- `client/web/front/src/features/agents/api.ts`
- `client/web/front/src/features/agents/pages/AgentListPage.tsx`
- `client/web/front/src/features/agents/components/CreateAgentDialog.tsx`

**新增测试**：

- Agent Skill 关联 API 测试。
- AgentProfile Repository 关联顺序测试。
- AgentFactory 加载已分配 Skill 测试。
- 不可用 Skill 不能被新 Agent 关联测试。

**验收**：

- 创建角色时可以多选 Skill，选择结果持久化。
- Agent 列表/详情返回 Skill 摘要。
- 创建角色页面不会扫描目录，不会触发刷新。
- Session 创建时 AgentFactory 能加载该 Agent 的 Skill 集合。
- Session 仍负责创建 Context，Agent 仍负责创建 Runtime。

### 阶段 6：PromptBuilder、Runtime 动态指令和资源边界

**目标**：Skill 真正影响模型输入，但不污染 Context 和权限体系。

**修改**：

- `code/agent/runtime/prompt_builder.py`
- `code/agent/runtime/runtime.py`（仅在动态输入接口确有需要时）
- `code/agent/runtime/agent.py`
- `code/agent/skills/skills.py`
- 可能涉及 `code/agent/head/llm.py` 的单轮输入接口。

**新增**：

- `code/agent/skills/skills.py`
- 动态指令和激活行为测试。
- Context 不污染回归测试。

**验收**：

- Agent 能看到已分配 Skill 的名称和描述。
- 当前激活 Skill 正文只进入当前模型输入。
- 下一轮未激活 Skill 不残留。
- Skill 正文不生成 Context 历史消息。
- 未配置 Skill 的 Agent 行为与改造前一致。
- Skill allowed-tools 不能增加 Agent 工具。
- Skill 脚本和资源不绕过权限流程。

### 阶段 7：完整回归、可观测性和收口

**目标**：验证完整链路并清理临时兼容代码。

**范围**：

- Python 单元测试、Repository/迁移测试、API 测试。
- 前端组件测试、API mock 测试和生产构建。
- 从导入/刷新到创建 Agent、创建 Session、运行任务的端到端验证。
- 检查日志中不出现 API Key、Skill 正文泄漏和服务器绝对路径。
- 记录一次刷新摘要和 Skill 加载失败原因，便于诊断。
- 如果阶段 5/6 完成后不再需要旧字段兼容，清理兼容分支并更新文档。

**最终验收**：

- 新用户可以从 Skill 目录刷新并在 Agent 创建时选择 Skill。
- 已有 Agent 和已有 Session 不因无 Skill 配置而回归。
- Skill 目录内容变更可以通过刷新被发现。
- 缺失或无效 Skill 有明确状态，不导致整个 Skill 列表不可用。
- Agent 的工具、权限和 Context 行为没有被 Skill 绕过或改变。

## 15. 测试计划

### 15.1 Parser/Catalog

- 有效 frontmatter + Markdown 正文。
- 缺少 frontmatter、缺少 `name`、缺少 `description`。
- YAML 语法错误、字段类型错误、未知字段。
- `allowed-tools` 字符串和数组格式。
- UTF-8、空正文、超长正文。
- `../`、绝对路径、符号链接和嵌套目录。
- 忽略 `.claude`、`.codex`、`.agents` 目录。

### 15.2 Storage

- 版本 5 升级到新版本。
- 新数据库创建完整表结构。
- Skill JSON 字段损坏时抛出 `StorageFormatError`。
- digest 相同不更新，digest 变化更新。
- Agent-Skill 顺序、去重、外键和删除约束。
- MISSING/INVALID/AVAILABLE 状态转换。

### 15.3 API

- Skill 列表分页/状态字段。
- 刷新统计准确且幂等。
- 导入 zip 路径穿越被拒绝。
- Agent 提交不存在、无效、缺失 Skill 时返回 422/404 等稳定错误。
- Skill 内容不出现在默认列表响应中。
- API 错误不泄露堆栈、绝对路径和密钥。

### 15.4 Runtime

- AgentFactory 能加载 Skill。
- PromptBuilder 能生成 Skill 元数据。
- 动态指令只作用于当前模型轮次。
- Skill 正文不追加到 Context。
- Skill 未配置时 Prompt 与原行为一致。
- allowed-tools 与 Agent tools 求交集。
- Skill 资源读取仍受路径和大小限制。

### 15.5 Frontend

- 设置导航和路由。
- Skill 列表加载、空状态、错误状态、刷新状态。
- 刷新摘要展示。
- 导入成功、同名冲突、无效 Skill 提示。
- 创建 Agent 多选 Skill、保持顺序、提交 ID。
- 已关联但缺失的 Skill 在编辑状态下回显警告。
- 生产构建和 TypeScript 类型检查通过。

## 16. 风险和处理

| 风险 | 影响 | 处理 |
| --- | --- | --- |
| Skill 正文全部注入 Prompt | Token 浪费、上下文污染、模型受无关指令影响 | 只注入元数据，正文按需激活 |
| 将 Skill 当 Tool 注册 | 破坏权限和函数调用边界 | Skill 不进入 ToolCatalog，不生成 schema |
| 只比较 mtime | 漏掉实际内容变更 | 计算整个目录 SHA-256 |
| 删除缺失 Skill 记录 | Agent 配置断裂、用户无法恢复 | 标记 MISSING，保留关联 |
| 任意路径读取资源 | 路径穿越、读取密钥 | 统一资源解析器并验证根目录 |
| Skill 脚本绕过 Bash 权限 | 写入或执行权限失控 | 脚本只通过现有 Tool/Permission 链路 |
| 运行时继续依赖 AgentProfile | storage 与 runtime 耦合 | Factory 转换为运行时 Skill 对象，Agent 不持有 Profile |
| 解析一个坏 Skill 中断全量刷新 | 其他 Skill 不可用 | 单项错误隔离并返回状态 |
| 动态 Prompt 残留到下一轮 | 任务间指令串扰 | 每轮显式构建临时 instructions，不写 Context |
| 关联无效 Skill 后 Agent 启动失败 | 既有 Agent 不可用 | 先约定明确策略；建议跳过并产生可诊断事件 |
| zip 压缩炸弹或目录穿越 | 本地文件被覆盖或资源耗尽 | 上传大小、解压总大小、路径和符号链接检查 |

## 17. 实施顺序和提交建议

建议按以下顺序提交，每个提交都保持可测试：

1. `新增 Skills 类型、解析器和目录 Catalog`
2. `新增 Skills 数据库表和 Repository`
3. `新增 Skills 同步与刷新服务`
4. `新增 Skills 设置页 API 和 UI`
5. `为 Agent 增加 Skills 配置和 Factory 装配`
6. `接入 Skills 动态模型指令`
7. `补齐 Skills 安全、回归测试和文档`

每个提交前执行与变更范围匹配的测试；最终执行完整 Python 测试、Web 测试、类型检查和构建。不得把 `.harness/state.db` 的用户已有修改暂存或提交。

## 18. 待实施前需要确认的决策

以下问题不阻塞计划文档，但在进入阶段 5/6 前必须形成明确结论：

1. Agent 关联的 `MISSING`/`INVALID` Skill 是允许 Agent 启动并跳过，还是阻止 Session 创建？建议允许启动并显示警告，以保护已有 Agent。
2. 当前任务的 Skill 激活是由 Runtime 参数显式传入，还是第一版暂时把所有已分配 Skill 的正文按需统一加载？建议保留动态激活接口，避免未来再改 Agent Loop。
3. `SkillProfile.instructions` 是否保存正文快照，还是每次运行从文件读取？本计划建议保存快照用于可恢复和一致性，同时用 digest 控制刷新；运行时必须确认目录仍可用。
4. “新增 Skill”是只支持目录选择，还是同时支持 zip 导入？本计划按两者都支持设计，但可先实现目录导入，再追加 zip。
5. 是否需要单独的 Skill 详情页？第一版可以先在列表展开或弹窗显示元数据，避免增加无必要路由。

## 19. 完成定义

只有同时满足以下条件，Skills 计划才可以从“未施工”改为“已完成”：

- 数据库迁移、Skill 索引和 Agent 关联都已实现并有测试。
- 固定目录刷新符合新增、更新、未变化、缺失、无效语义。
- 设置页可以查看、刷新和导入 Skill。
- 创建/编辑 Agent 可以多选并持久化 Skill。
- Session 创建的 Agent 能正确加载所选 Skill。
- Skill 指令进入模型当前输入但不污染 Context。
- Skill 不能绕过 Tool、PermissionManager、Session 权限或工作目录限制。
- Windows 和 macOS 下固定目录、路径规范化和资源安全测试通过。
- API、前端类型检查、前端构建和完整回归测试通过。
- 文档中的兼容分支、临时代码和未施工标记已根据实际实现收口。
