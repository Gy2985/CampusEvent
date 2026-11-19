"""报名策略的具体实现与注册表（工厂）。

新增一种报名方式（例如“限额抽签”“邀请制”）时，只需：
1. 新增一个 ``RegistrationPolicy`` 子类；
2. 在 ``build_default_registry`` 中登记；
业务服务、页面、数据库表的 policy_type 取值同步扩展即可，
``RegistrationService`` 不需要修改——这正是策略模式要表达的“对扩展开放”。
"""
from __future__ import annotations

from ..domain.entities import PolicyType, RegistrationStatus
from ..domain.errors import ValidationError
from .base import RegistrationContext, RegistrationDecision, RegistrationPolicy


class DirectRegistrationPolicy(RegistrationPolicy):
    """直接报名：名额充足即可自动通过。"""

    policy_type = PolicyType.DIRECT
    requires_immediate_capacity_check = True

    def decide(self, context: RegistrationContext) -> RegistrationDecision:
        return RegistrationDecision(
            status=RegistrationStatus.APPROVED,
            student_message=f"报名成功：{context.activity.title}（直接报名，已自动通过）。",
        )


class ApprovalRegistrationPolicy(RegistrationPolicy):
    """审核型报名：提交后进入待审核，由管理员批准或拒绝。"""

    policy_type = PolicyType.APPROVAL
    # 待审核报名不占用名额，因此提交时不做名额拦截，审批时再检查
    requires_immediate_capacity_check = False

    def decide(self, context: RegistrationContext) -> RegistrationDecision:
        return RegistrationDecision(
            status=RegistrationStatus.PENDING,
            student_message=f"报名已提交：{context.activity.title}（等待管理员审核）。",
        )


class PolicyRegistry:
    """策略注册表：把活动上的 policy_type 映射为策略对象。"""

    def __init__(self, policies: list[RegistrationPolicy] | None = None):
        self._policies: dict[PolicyType, RegistrationPolicy] = {}
        for policy in policies or []:
            self.register(policy)

    def register(self, policy: RegistrationPolicy) -> None:
        if policy.policy_type in self._policies:
            raise ValueError(f"策略重复注册：{policy.policy_type}")
        self._policies[policy.policy_type] = policy

    def get(self, policy_type: PolicyType | str) -> RegistrationPolicy:
        key = policy_type if isinstance(policy_type, PolicyType) else PolicyType(policy_type)
        policy = self._policies.get(key)
        if policy is None:
            raise ValidationError(f"未知的报名方式：{policy_type}")
        return policy

    def all(self) -> list[RegistrationPolicy]:
        return list(self._policies.values())


def build_default_registry() -> PolicyRegistry:
    """初始版本的策略装配。"""
    return PolicyRegistry([DirectRegistrationPolicy(), ApprovalRegistrationPolicy()])
