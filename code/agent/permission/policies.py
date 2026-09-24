"""权限决策中不依赖规则存储的纯策略。

策略只回答某类请求是否应被硬拒绝、要求确认或按模式处理；规则的
保存和优先级由 PermissionManager 负责。把它们拆开后，安全边界可被
独立测试，也不会让规则表意外绕过硬安全限制。
"""

import os
import re
from collections.abc import Iterable

from permission.types import PermissionAction, PermissionDecision, PermissionMode, PermissionRequest


def _normalise_absolute_path(path: str) -> str:
    """返回用于策略比较的规范化绝对路径。

    Args:
        path: 调用方提供的文件或目录路径。

    Returns:
        消除 ``.``、``..`` 和重复分隔符后的绝对路径。

    Raises:
        TypeError: path 不是字符串时抛出。
        ValueError: path 不是绝对路径时抛出。

    路径规范化仅保证字符串比较一致；软链接解析和真正的文件系统
    隔离属于后续 harness 安全层，不能被误认为已在这里完成。
    """
    if not isinstance(path, str):
        raise TypeError("路径必须是字符串")
    if not os.path.isabs(path):
        raise ValueError("权限策略只接受绝对路径")
    return os.path.normpath(os.path.abspath(path))


def _is_path_within(path: str, root: str) -> bool:
    """判断 path 是否等于 root 或位于 root 子树中。
    判断path是否在指定的资源目录下

    Args:
        path: 已规范化的目标路径。
        root: 已规范化的根目录路径。

    Returns:
        目标位于根目录本身或其子树时返回 True。

    使用 ``commonpath`` 而不是字符串 ``startswith``，防止 `/src` 错误
    匹配 `/src-other`。不同 Windows 磁盘符时 commonpath 会抛异常，此时
    两者不属于同一棵目录树。
    """
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:
        return False


class HardSafetyPolicy:
    """
    强制安全规则
    无条件拒绝少量、明确且不可接受的高危操作。

    Attributes:
        _critical_write_paths: 绝不允许通过文件工具修改的关键系统文件。

    本类刻意不尝试完整解析 shell。对于 bash，仅匹配几个明确的整条
    命令形式；未命中的命令仍由受保护策略、规则和模式控制。
    """

    # 这些文件的修改会直接影响认证或权限提升，不能由 yolo 或普通规则覆盖。
    DEFAULT_CRITICAL_WRITE_PATHS = frozenset({
        "/etc/passwd",
        "/etc/shadow",
        "/etc/sudoers",
        "/private/etc/master.passwd",
    })

    # 只匹配完整根目录递归删除命令，避免把 `echo "rm -rf /"` 等文本误杀。
    _ROOT_DELETE_COMMAND = re.compile(
        r"^\s*(?:sudo\s+)?rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/\*?\s*$"
    )

    def __init__(self, critical_write_paths: Iterable[str] | None = None) -> None:
        """创建硬安全策略。

        Args:
            critical_write_paths: 可选的关键文件集合；为空时使用内置的
                小范围默认集，便于平台或测试按需扩展。
        """
        paths = critical_write_paths or self.DEFAULT_CRITICAL_WRITE_PATHS
        self._critical_write_paths = frozenset(
            _normalise_absolute_path(path) for path in paths
        )

    def check(
        self,
        request: PermissionRequest,
        *,
        command: str | None = None,
    ) -> PermissionDecision | None:
        """检查请求是否命中绝对拒绝规则。

        Args:
            request: 已构造的实际权限请求。
            command: bash 的原始命令文本，只用于有限的明确黑名单匹配；
                它不会存入 PermissionRule，也不用于推导文件资源。

        Returns:
            命中硬安全边界时返回 DENY；不命中返回 None，以便调用方继续
            执行受保护资源、显式规则和模式策略。
        """
        if (
            request.action is PermissionAction.FILE_WRITE
            and request.resource in self._critical_write_paths
        ):
            return PermissionDecision.DENY

        if (
            request.action is PermissionAction.BASH_EXECUTE
            and command is not None
            and self._ROOT_DELETE_COMMAND.fullmatch(command)
        ):
            return PermissionDecision.DENY

        return None


class ProtectedResourcePolicy:
    """要求用户确认、但不绝对禁止访问的系统资源策略。

    Attributes:
        _protected_roots: 需要确认的规范化目录根集合。

    该策略优先于用户 allow 规则和权限模式，避免宽泛目录授权或 yolo
    无意覆盖系统区域。用户仍可在 Runtime 的 ASK 流程中明确确认。
    """

    DEFAULT_PROTECTED_ROOTS = (
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/Library",
        "/private",
        "/proc",
        "/root",
        "/sbin",
        "/sys",
        "/System",
        "/usr",
        "/var",
    )

    def __init__(self, protected_roots: Iterable[str] | None = None) -> None:
        """创建受保护资源策略。

        Args:
            protected_roots: 可选的受保护目录根；为空时使用常见 Unix/macOS
                系统目录。调用方传入的路径必须是绝对路径。
        """
        roots = protected_roots or self.DEFAULT_PROTECTED_ROOTS
        self._protected_roots = tuple(
            _normalise_absolute_path(root) for root in roots
        )

    def requires_confirmation(self, request: PermissionRequest) -> bool:
        """判断文件读取或写入是否位于受保护目录中。

        Args:
            request: 已规范化资源的权限请求。

        Returns:
            文件读写目标位于受保护目录时返回 True；没有文件资源的 bash
            由其自身动作策略处理，返回 False。
        """
        if request.action not in {
            PermissionAction.FILE_READ,
            PermissionAction.FILE_WRITE,
        }:
            return False
        if request.resource is None:
            return False
        return any(
            _is_path_within(request.resource, root)
            for root in self._protected_roots
        )


class ModePolicy:
    """在未命中硬策略或显式规则时提供模式默认决定。

    Attributes:
        _project_path: 当前 Session 项目目录的规范化绝对路径，用于识别项目外
            文件资源。它用于默认决策，不是路径安全沙箱。
    """

    def __init__(self, project_path: str | None) -> None:
        """创建工作区相关的模式策略。

        Args:
            project_path: 当前 Session 的项目目录，必须是绝对路径。
        """
        self._project_path = (
            _normalise_absolute_path(project_path) if project_path else None
        )

    def decide(
        self,
        mode: PermissionMode,
        request: PermissionRequest,
    ) -> PermissionDecision:
        """根据模式和实际资源返回默认权限决定。

        Args:
            mode: 当前 Agent 的权限模式。
            request: 未命中硬策略、受保护策略和显式规则的请求。

        Returns:
            该模式对此类普通请求的默认 allow、deny 或 ask 决定。

        项目外资源先于动作表处理：PLAN 拒绝，BUILD 要求确认，YOLO 允许。
        bash 的 resource 为 None，因此直接使用动作表，不会伪造项目内外
        归属。
        """
        if request.action in {
            PermissionAction.PROCESS_INSPECT,
            PermissionAction.PROCESS_STOP,
        }:
            return PermissionDecision.ALLOW
        if self._project_path is None:
            return PermissionDecision.DENY
        if request.resource is not None and not _is_path_within(
            request.resource, self._project_path
        ):
            return {
                PermissionMode.PLAN: PermissionDecision.DENY,
                PermissionMode.BUILD: PermissionDecision.ASK,
                PermissionMode.YOLO: PermissionDecision.ALLOW,
            }[mode]

        decisions = {
            PermissionMode.PLAN: {
                PermissionAction.FILE_READ: PermissionDecision.ALLOW,
                PermissionAction.FILE_WRITE: PermissionDecision.DENY,
                PermissionAction.BASH_EXECUTE: PermissionDecision.DENY,
            },
            PermissionMode.BUILD: {
                PermissionAction.FILE_READ: PermissionDecision.ALLOW,
                PermissionAction.FILE_WRITE: PermissionDecision.ALLOW,
                PermissionAction.BASH_EXECUTE: PermissionDecision.ASK,
            },
            PermissionMode.YOLO: {
                PermissionAction.FILE_READ: PermissionDecision.ALLOW,
                PermissionAction.FILE_WRITE: PermissionDecision.ALLOW,
                PermissionAction.BASH_EXECUTE: PermissionDecision.ALLOW,
            },
        }
        return decisions[mode][request.action]
