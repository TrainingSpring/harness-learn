"""Session 权限规则的匹配与最终决策入口。"""

import os
from typing import Protocol

from permission.policies import HardSafetyPolicy, ModePolicy, ProtectedResourcePolicy
from permission.types import (
    PermissionDecision,
    PermissionMode,
    PermissionRequest,
    PermissionRule,
    PermissionScope,
)


class SessionPermissionRuleStore(Protocol):
    def list_for_session(self, session_id: str) -> list[PermissionRule]: ...

    def save(self, rule: PermissionRule) -> PermissionRule: ...


class PermissionManager:
    """按硬策略、Session 规则和模式决定一次工具调用是否可执行。"""

    def __init__(
        self,
        mode: PermissionMode,
        session_id: str,
        project_path: str | None,
        rule_repository: SessionPermissionRuleStore | None = None,
        hard_safety_policy: HardSafetyPolicy | None = None,
        protected_resource_policy: ProtectedResourcePolicy | None = None,
    ) -> None:
        if not session_id:
            raise ValueError("session_id 不能为空")
        self._mode = mode
        self._session_id = session_id
        self._rule_repository = rule_repository
        self._rules = (
            list(rule_repository.list_for_session(session_id))
            if rule_repository
            else []
        )
        self._hard_safety_policy = hard_safety_policy or HardSafetyPolicy()
        self._protected_resource_policy = protected_resource_policy or ProtectedResourcePolicy()
        self._mode_policy = ModePolicy(project_path)

    def check(
        self,
        request: PermissionRequest,
        *,
        command: str | None = None,
    ) -> PermissionDecision:
        self._require_session(request)
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
    ) -> PermissionRule | None:
        return self._write_rule(request, PermissionDecision.ALLOW, scope, resource)

    def deny(
        self,
        request: PermissionRequest,
        *,
        scope: PermissionScope,
        resource: str | None,
    ) -> PermissionRule | None:
        return self._write_rule(request, PermissionDecision.DENY, scope, resource)

    def _write_rule(
        self,
        request: PermissionRequest,
        decision: PermissionDecision,
        scope: PermissionScope,
        resource: str | None,
    ) -> PermissionRule | None:
        self._require_session(request)
        if scope is PermissionScope.ONCE:
            return None
        if scope is not PermissionScope.SESSION:
            raise ValueError("权限确认只支持 once 或 session")
        rule = PermissionRule(
            action=request.action,
            resource=self._validate_rule_resource(request, resource),
            decision=decision,
            session_id=request.session_id,
        )
        if self._rule_repository is not None:
            rule = self._rule_repository.save(rule)
        self._replace_rule(rule)
        return rule

    def _find_matching_rule(self, request: PermissionRequest) -> PermissionRule | None:
        matched = [rule for rule in self._rules if self._rule_matches(rule, request)]
        return max(matched, key=self._rule_priority) if matched else None

    @staticmethod
    def _rule_matches(rule: PermissionRule, request: PermissionRequest) -> bool:
        return (
            rule.action is request.action
            and rule.session_id == request.session_id
            and PermissionManager._resource_matches(rule.resource, request.resource)
        )

    @staticmethod
    def _resource_matches(rule_resource: str | None, request_resource: str | None) -> bool:
        if rule_resource is None or request_resource is None:
            return rule_resource is None and request_resource is None
        return PermissionManager._is_path_within(
            PermissionManager._normalise_absolute_path(request_resource),
            PermissionManager._normalise_absolute_path(rule_resource),
        )

    @staticmethod
    def _validate_rule_resource(
        request: PermissionRequest,
        resource: str | None,
    ) -> str | None:
        if request.resource is None:
            if resource is not None:
                raise ValueError("无资源请求只能写入 resource=None 的规则")
            return None
        if resource is None:
            raise ValueError("文件资源请求必须指定规则资源")
        request_resource = PermissionManager._normalise_absolute_path(request.resource)
        rule_resource = PermissionManager._normalise_absolute_path(resource)
        if not PermissionManager._is_path_within(request_resource, rule_resource):
            raise ValueError("规则资源必须覆盖当前权限请求")
        return rule_resource

    @staticmethod
    def _rule_priority(rule: PermissionRule) -> int:
        if rule.resource is None:
            return 0
        return len(PermissionManager._normalise_absolute_path(rule.resource).split(os.sep))

    def _replace_rule(self, new_rule: PermissionRule) -> None:
        self._rules = [
            rule
            for rule in self._rules
            if not (
                rule.action is new_rule.action
                and rule.resource == new_rule.resource
                and rule.session_id == new_rule.session_id
            )
        ]
        self._rules.append(new_rule)

    def _require_session(self, request: PermissionRequest) -> None:
        if request.session_id != self._session_id:
            raise ValueError("权限请求不属于当前 Session")

    @staticmethod
    def _normalise_absolute_path(path: str) -> str:
        if not isinstance(path, str) or not os.path.isabs(path):
            raise ValueError("权限规则资源必须是绝对路径")
        return os.path.normpath(os.path.abspath(path))

    @staticmethod
    def _is_path_within(path: str, root: str) -> bool:
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False
