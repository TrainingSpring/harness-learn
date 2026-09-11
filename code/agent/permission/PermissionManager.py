"""内存权限规则的写入、匹配与最终决策入口。"""

import os

from permission.policies import (
    HardSafetyPolicy,
    ModePolicy,
    ProtectedResourcePolicy,
)
from permission.types import (
    PermissionDecision,
    PermissionMode,
    PermissionRequest,
    PermissionRule,
    PermissionScope,
)


class PermissionManager:
    """根据安全策略、显式规则和模式为一次调用作出权限决定。

    Attributes:
        _mode: 未命中硬策略和规则时采用的默认权限模式。
        _rules: 当前进程内的授权规则；首版不会持久化到磁盘。
        _hard_safety_policy: 不可被 yolo 或用户规则覆盖的绝对拒绝策略。
        _protected_resource_policy: 命中后仍可由用户确认、但不能自动放行的
            受保护资源策略。
        _mode_policy: 将工作区与模式默认表结合的无状态默认策略。
    """

    _SCOPE_PRIORITY = {
        PermissionScope.ONCE: 3,
        PermissionScope.SESSION: 2,
        PermissionScope.AGENT: 1,
    }

    def __init__(
        self,
        mode: PermissionMode,
        workspace: str,
        hard_safety_policy: HardSafetyPolicy | None = None,
        protected_resource_policy: ProtectedResourcePolicy | None = None,
    ) -> None:
        """创建使用内存规则表的权限管理器。

        Args:
            mode: 当前 Agent 的默认权限模式。
            workspace: 用于模式策略判断项目内外资源的绝对工作目录。
            hard_safety_policy: 可选的绝对拒绝策略；未传入时使用默认策略。
            protected_resource_policy: 可选的受保护资源策略；未传入时使用
                默认系统目录策略。

        Manager 不持有 ExecutionContext。实际调用的 call/session/agent 身份
        都在 PermissionRequest 中提供，因此这里可以作为纯领域对象测试。
        """
        self._mode = mode # 权限模式
        self._rules: list[PermissionRule] = [] # 规则列表
        self._hard_safety_policy = ( # 绝对拒绝策略
            hard_safety_policy
            if hard_safety_policy is not None
            else HardSafetyPolicy()
        )
        self._protected_resource_policy = ( # 受保护资源策略
            protected_resource_policy
            if protected_resource_policy is not None
            else ProtectedResourcePolicy()
        )
        self._mode_policy = ModePolicy(workspace) # 模式策略

    def check(
        self,
        request: PermissionRequest,
        *,
        command: str | None = None,
    ) -> PermissionDecision:
        """按固定优先级返回一次工具调用的权限决定。

        Args:
            request: 已解析出动作、资源和调用身份的真实权限请求。
            command: bash 的原始命令，仅传给有限的硬安全黑名单匹配；不
                会保存到规则中，也不会作为资源匹配依据。

        Returns:
            ALLOW 表示 Runtime 可以执行工具，DENY 表示 Runtime 应写入
            标准工具失败结果，ASK 表示 Runtime 必须暂停并等待用户确认。

        判断顺序不能调整：硬安全与受保护资源必须在规则和 yolo 模式之前，
        否则宽泛授权会意外突破系统安全边界。
        """
        hard_decision = self._hard_safety_policy.check(request, command=command)
        if hard_decision is not None:
            return hard_decision

        if self._protected_resource_policy.requires_confirmation(request):
            return PermissionDecision.ASK

        rule = self._find_matching_rule(request)
        if rule is not None:
            return rule.decision

        return self._mode_policy.decide(self._mode, request)

    def grant(
        self,
        request: PermissionRequest,
        *,
        scope: PermissionScope,
        resource: str | None,
    ) -> PermissionRule:
        """根据原请求写入一条允许规则。

        Args:
            request: 用户刚刚确认的真实权限请求，提供可信身份字段。
            scope: 用户选择的规则生效范围。
            resource: UI/Runtime 选择的授权资源根；文件操作通常是目标父
                目录，bash 等无资源动作传入 None。

        Returns:
            写入后生效的 PermissionRule。
        """
        return self._write_rule(
            request=request,
            decision=PermissionDecision.ALLOW,
            scope=scope,
            resource=resource,
        )

    def deny(
        self,
        request: PermissionRequest,
        *,
        scope: PermissionScope,
        resource: str | None,
    ) -> PermissionRule:
        """根据原请求写入一条拒绝规则。

        Args:
            request: 用户刚刚确认的真实权限请求，提供可信身份字段。
            scope: 用户选择的规则生效范围。
            resource: 拒绝规则覆盖的资源根；必须实际覆盖本次请求资源。

        Returns:
            写入后生效的 PermissionRule。
        """
        return self._write_rule(
            request=request,
            decision=PermissionDecision.DENY,
            scope=scope,
            resource=resource,
        )

    def _write_rule(
        self,
        *,
        request: PermissionRequest,
        decision: PermissionDecision,
        scope: PermissionScope,
        resource: str | None,
    ) -> PermissionRule:
        """构造规则并替换同一作用域、资源和主体的旧规则。

        Args:
            request: 作为规则主体来源的权限请求。
            decision: 需要保存的允许或拒绝决定。
            scope: 规则的生效范围。
            resource: 经 Runtime 确定的授权资源根。

        Returns:
            已保存到内存规则表的规则。

        私有方法集中 grant/deny 的共同逻辑，确保两种决定使用完全一致的
        主体绑定与资源校验，不会出现一边可越权而另一边不可越权的偏差。
        """
        normalized_resource = self._validate_rule_resource(request, resource)
        identity_kwargs = self._scope_identity_kwargs(request, scope)
        rule = PermissionRule(
            action=request.action,
            resource=normalized_resource,
            decision=decision,
            scope=scope,
            **identity_kwargs,
        )
        self._replace_rule(rule)
        return rule

    @staticmethod
    def _scope_identity_kwargs(
        request: PermissionRequest,
        scope: PermissionScope,
    ) -> dict[str, str]:
        """从请求派生某种 scope 唯一允许写入的身份字段。

        Args:
            request: 当前实际权限请求。
            scope: 即将写入的规则范围。

        Returns:
            可直接传给 PermissionRule 的一个身份字段字典。
        """
        if scope is PermissionScope.ONCE:
            return {"call_id": request.call_id}
        if scope is PermissionScope.SESSION:
            return {"session_id": request.session_id}
        return {"agent_id": request.agent_id}

    @staticmethod
    def _validate_rule_resource(
        request: PermissionRequest,
        resource: str | None,
    ) -> str | None:
        """验证规则资源确实覆盖本次请求，并将它规范化。

        Args:
            request: 需要被规则覆盖的原始请求。
            resource: 调用方希望写入规则的资源根。

        Returns:
            规范化后的资源根，或无资源动作的 None。

        Raises:
            ValueError: 资源类型、绝对路径要求或覆盖关系不合法时抛出。

        不允许给 `/workspace/a.py` 的确认写入 `/outside` 规则：确认界面只能
        收窄或覆盖当前请求，不能借一次确认扩展到无关路径。
        """
        if request.resource is None:
            if resource is not None:
                raise ValueError("无资源请求只能写入 resource=None 的规则")
            return None

        if resource is None:
            raise ValueError("文件资源请求必须指定规则资源")

        request_resource = PermissionManager._normalise_absolute_path(request.resource)
        rule_resource = PermissionManager._normalise_absolute_path(resource)
        if not PermissionManager._is_path_within(request_resource, rule_resource):
            raise ValueError("规则资源必须覆盖当前权限请求的资源")
        return rule_resource

    def _find_matching_rule(
        self,
        request: PermissionRequest,
    ) -> PermissionRule | None:
        """寻找对请求最具体、优先级最高的显式规则。

        Args:
            request: 要匹配的真实权限请求。

        Returns:
            最匹配的规则；没有任何命中时返回 None。

        先比较 scope（ONCE > SESSION > AGENT），再比较资源路径深度。旧规则
        在写入时已经被同槽位的新规则替换，因此不会依赖 list 遍历顺序。
        """
        matched_rules = [
            rule for rule in self._rules if self._rule_matches(rule, request)
        ]
        if not matched_rules:
            return None
        return max(matched_rules, key=self._rule_priority)

    def _rule_matches(
        self,
        rule: PermissionRule,
        request: PermissionRequest,
    ) -> bool:
        """判断一条规则是否同时匹配动作、主体和资源范围。"""
        if rule.action is not request.action:
            return False
        if not self._scope_matches(rule, request):
            return False
        return self._resource_matches(rule.resource, request.resource)

    @staticmethod
    def _scope_matches(rule: PermissionRule, request: PermissionRequest) -> bool:
        """根据规则 scope 比较唯一对应的请求身份字段。"""
        if rule.scope is PermissionScope.ONCE:
            return rule.call_id == request.call_id
        if rule.scope is PermissionScope.SESSION:
            return rule.session_id == request.session_id
        return rule.agent_id == request.agent_id

    @staticmethod
    def _resource_matches(
        rule_resource: str | None,
        request_resource: str | None,
    ) -> bool:
        """按目录子树边界匹配规则资源和实际资源。

        `None` 只匹配同样为 `None` 的无资源动作。文件路径使用 commonpath，
        防止字符串前缀把 `/src-other` 误判为 `/src` 子目录。
        """
        if rule_resource is None or request_resource is None:
            return rule_resource is None and request_resource is None
        return PermissionManager._is_path_within(
            PermissionManager._normalise_absolute_path(request_resource),
            PermissionManager._normalise_absolute_path(rule_resource),
        )

    @classmethod
    def _rule_priority(cls, rule: PermissionRule) -> tuple[int, int]:
        """生成用于选择最具体规则的稳定优先级元组。"""
        resource_depth = 0 if rule.resource is None else len(
            cls._normalise_absolute_path(rule.resource).split(os.sep)
        )
        return cls._SCOPE_PRIORITY[rule.scope], resource_depth

    def _replace_rule(self, new_rule: PermissionRule) -> None:
        """替换同一动作、资源、scope 与主体的旧规则。

        Args:
            new_rule: 已校验、即将生效的新规则。

        规则表只保留每个“规则槽位”的最新选择，避免匹配结果隐式依赖
        规则写入列表的先后顺序。
        """
        self._rules = [
            rule for rule in self._rules if not self._same_rule_slot(rule, new_rule)
        ]
        self._rules.append(new_rule)

    @staticmethod
    def _same_rule_slot(left: PermissionRule, right: PermissionRule) -> bool:
        """判断两条规则是否会争夺同一个可替换规则槽位。"""
        if (
            left.action is not right.action
            or left.resource != right.resource
            or left.scope is not right.scope
        ):
            return False
        if left.scope is PermissionScope.ONCE:
            return left.call_id == right.call_id
        if left.scope is PermissionScope.SESSION:
            return left.session_id == right.session_id
        return left.agent_id == right.agent_id

    @staticmethod
    def _normalise_absolute_path(path: str) -> str:
        """规范化绝对路径，拒绝将相对路径混入权限规则。"""
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("权限规则资源必须是绝对路径")
        return os.path.normpath(os.path.abspath(path))

    @staticmethod
    def _is_path_within(path: str, root: str) -> bool:
        """安全比较两个路径的目录归属，不使用脆弱的字符串前缀。"""
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False



