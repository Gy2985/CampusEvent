"""邮件发送端口（端口—适配器，v2 / CR-02）。

为什么单独建一个 ``ports`` 层：
* 观察者只依赖 ``EmailSender`` 这个**接口**，不依赖 SMTP、不依赖具体厂商；
* 教学环境用 ``MockEmailSender``（不连外网、可注入故障），生产环境替换为真实实现；
* 换实现只改装配（``create_app``），业务代码与观察者一行不改。

Mock 的"故障注入"是刻意设计的：CR2-03 要验证"邮件失败不回滚报名、错误可查"，
如果没有可控故障源，这条需求就只能靠嘴说。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    """一封待发送的邮件（值对象，便于测试断言）。"""

    to_addr: str
    subject: str
    body: str


class EmailDeliveryError(Exception):
    """邮件发送失败（真实实现里对应 SMTP 拒绝、超时、配额耗尽等）。"""


class EmailSender(Protocol):
    """端口：任何实现只要满足 ``send`` 语义即可插拔。"""

    def send(self, message: EmailMessage) -> None:  # pragma: no cover - 协议声明
        ...


class MockEmailSender:
    """模拟发送器：只做校验与"记录"，不发真实邮件。

    * ``fail_recipients``：命中这些收件人时抛出 :class:`EmailDeliveryError`，用于演示/测试故障；
    * ``always_fail``：全部失败，便于整体切换"邮件服务不可用"场景。
    """

    def __init__(
        self,
        fail_recipients: set[str] | None = None,
        always_fail: bool = False,
    ) -> None:
        self.fail_recipients = set(fail_recipients or ())
        self.always_fail = always_fail
        #: 记录"曾经尝试发送过什么"，便于课堂演示与调试（正式记录在 email_outbox 表）
        self.outbox: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> None:
        if not message.to_addr or "@" not in message.to_addr:
            raise EmailDeliveryError(f"收件人地址不合法：{message.to_addr!r}")
        if self.always_fail or message.to_addr in self.fail_recipients:
            raise EmailDeliveryError("模拟故障：SMTP 服务器连接超时（421 Service not available）")
        self.outbox.append(message)
