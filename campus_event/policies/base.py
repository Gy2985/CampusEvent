"""报名策略的稳定抽象（策略模式）。

设计说明（对应附录 B.3 检查表第 2 条）：
* ``RegistrationPolicy`` 是抽象策略，只负责回答“这类活动提交报名后，
* 报名记录应该进入哪个状态”，并给出面向学生的一句话文案。
* 名额是否已满属于**所有活动共有**的公共约束，因此放在 ``RegistrationService``
* 统一执行；策略只通过 ``requires_immediate_capacity_check`` 声明：
* “本策略是否必须在提交时立刻检查名额”。直接报名必须立刻检查（否则会产生
* 超出容量的“已通过”记录），审核型报名则允许在满员时继续排队，由审批环节
* 二次检查。这样既避免了在服务主流程里写 ``if 活动类型 == ...``，也没有把
* 公共规则泄漏进策略实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from ..domain.entities import Activity, PolicyType, RegistrationStatus, Student


@dataclass(frozen=True)
class RegistrationContext:
    """策略决策所需的上下文（只读数据，策略不做任何数据库访问）。"""

    activity: Activity
    student: Student
    approved_count: int
    now: datetime

    @property
    def remaining(self) -> int:
        return max(self.activity.capacity - self.approved_count, 0)

    @property
    def is_full(self) -> bool:
        return self.approved_count >= self.activity.capacity


@dataclass(frozen=True)
class RegistrationDecision:
    """策略决策结果：目标状态 + 给学生的通知文案。"""

    status: RegistrationStatus
    student_message: str


class RegistrationPolicy(ABC):
    """报名策略抽象。"""

    policy_type: PolicyType

    #: 提交报名时是否必须立即检查名额
    requires_immediate_capacity_check: bool = True

    @abstractmethod
    def decide(self, context: RegistrationContext) -> RegistrationDecision:
        """根据上下文决定报名记录的初始状态。"""
