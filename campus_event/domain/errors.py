"""业务异常定义。

所有可预期的业务规则失败都用 BusinessError 子类表达，由 Web 层统一转换为
面向用户的提示，而不会抛出 500 错误或写入脏数据。
"""
from __future__ import annotations


class BusinessError(Exception):
    """业务规则失败基类。"""

    code = "BUSINESS_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(BusinessError):
    """输入校验失败。"""

    code = "VALIDATION_ERROR"


class NotFoundError(BusinessError):
    """对象不存在。"""

    code = "NOT_FOUND"


class PermissionDeniedError(BusinessError):
    """当前身份无权执行该操作。"""

    code = "PERMISSION_DENIED"


class DuplicateRegistrationError(BusinessError):
    """同一活动已存在有效报名。"""

    code = "DUPLICATE_REGISTRATION"


class CapacityExceededError(BusinessError):
    """名额已满。"""

    code = "CAPACITY_EXCEEDED"


class RegistrationClosedError(BusinessError):
    """活动已开始或已结束，不允许报名。"""

    code = "REGISTRATION_CLOSED"


class InvalidStateTransitionError(BusinessError):
    """报名状态不允许当前操作。"""

    code = "INVALID_STATE_TRANSITION"


class GradeRestrictedError(BusinessError):
    """v2（CR-01）：年级不满足活动的资格限定。"""

    code = "GRADE_RESTRICTED"
