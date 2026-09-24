"""工具调用期间共享、不可变的执行环境。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionContext:
    """描述一次 Agent 会话中工具运行所需的环境信息。

    Attributes:
        project_path: 用户为当前 Session 选择的项目目录；为空时不能执行项目工具。
        agent_id: 稳定的逻辑 Agent 标识，用于执行记录，不参与授权归属。
        session_id: 当前交互会话标识。
        max_tool_call_length: 单次工具文本输出允许返回给模型的最大字符数。
        max_read_lines: 单次文本读取允许返回的最大行片段数。
        max_directory_entries: 单次目录读取允许返回的最大条目数。
        max_image_bytes: 单张图片允许读入内存的最大字节数。
        max_write_bytes: 单次文本文件允许写入的最大 UTF-8 字节数。
        max_edit_source_bytes: Edit 完整读取源文本时允许的最大字节数。
        max_edit_operations: 单次 Edit 调用允许的最大替换条数。
        file_mutation_lock_timeout_seconds: 等待同进程文件提交锁的最长秒数。
    """

    project_path: str | None
    agent_id: str
    session_id: str
    max_tool_call_length: int = 20_000
    max_read_lines: int = 1_000
    max_directory_entries: int = 500
    max_image_bytes: int = 10 * 1024 * 1024
    max_write_bytes: int = 2 * 1024 * 1024
    max_edit_source_bytes: int = 2 * 1024 * 1024
    max_edit_operations: int = 100
    file_mutation_lock_timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        """尽早拒绝缺少身份或非法项目目录的执行上下文。"""
        if self.project_path is not None and not self.project_path:
            raise ValueError("project_path 必须是非空路径或 None")
        if not self.agent_id:
            raise ValueError("agent_id 不能为空")
        if not self.session_id:
            raise ValueError("session_id 不能为空")
        if self.max_tool_call_length <= 0:
            raise ValueError("max_tool_call_length 必须大于 0")
        if self.max_read_lines <= 0:
            raise ValueError("max_read_lines 必须大于 0")
        if self.max_directory_entries <= 0:
            raise ValueError("max_directory_entries 必须大于 0")
        if self.max_image_bytes <= 0:
            raise ValueError("max_image_bytes 必须大于 0")
        if self.max_write_bytes <= 0:
            raise ValueError("max_write_bytes 必须大于 0")
        if self.max_edit_source_bytes <= 0:
            raise ValueError("max_edit_source_bytes 必须大于 0")
        if self.max_edit_operations <= 0:
            raise ValueError("max_edit_operations 必须大于 0")
        if self.file_mutation_lock_timeout_seconds <= 0:
            raise ValueError("file_mutation_lock_timeout_seconds 必须大于 0")
