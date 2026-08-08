"""SMTP 邮件发送封装。

基于 Python 标准库 smtplib，零第三方依赖。支持：
- SSL（端口 465）与 STARTTLS（端口 587）自动切换
- HTML + 纯文本双正文
- 多收件人（SMTP_TO 逗号分隔）

使用方式：
    from agents._shared.emailer import send_email, SMTPConfig
    send_email(
        SMTPConfig.from_env(),
        to=["you@example.com"],
        subject="日报",
        html_body="<h1>...</h1>",
        text_body="...",
    )
"""

import os
import smtplib
from dataclasses import dataclass, field
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate


class EmailError(RuntimeError):
    """邮件发送失败。"""


@dataclass
class SMTPConfig:
    """SMTP 发送配置。

    Attributes
    ----------
    host : str
        SMTP 服务器地址（如 smtp.qq.com / smtp.exmail.qq.com）。
    port : int
        端口（465=SSL，587=STARTTLS）。
    user : str
        发件邮箱地址。
    password : str
        邮箱授权码（不是登录密码）。
    to : list of str
        收件人邮箱列表。
    """

    host: str
    port: int
    user: str
    password: str
    to: list[str] = field(default_factory=lambda: [])

    @classmethod
    def from_env(cls) -> "SMTPConfig":
        """从环境变量读取 SMTP 配置。

        必需环境变量：SMTP_HOST、SMTP_PORT、SMTP_USER、SMTP_PASSWORD、SMTP_TO。
        SMTP_TO 支持逗号分隔多个收件人。

        Returns
        -------
        SMTPConfig
            从环境变量构建的 SMTP 配置。

        Raises
        ------
        EmailError
            缺少任一必需环境变量。
        """
        host = os.environ.get("SMTP_HOST", "")
        port = int(os.environ.get("SMTP_PORT", "0") or 0)
        user = os.environ.get("SMTP_USER", "")
        password = os.environ.get("SMTP_PASSWORD", "")
        to_raw = os.environ.get("SMTP_TO", "")

        # 收集所有缺失项，一次性报错（便于用户一次性补齐）
        # port 是 int，统一转为 str 参与 falsy 判定（0 也视为缺失）
        missing = [
            k for k, v in [
                ("SMTP_HOST", host),
                ("SMTP_PORT", str(port)),
                ("SMTP_USER", user),
                ("SMTP_PASSWORD", password),
                ("SMTP_TO", to_raw),
            ] if not v
        ]
        if missing:
            raise EmailError(f"缺少环境变量: {', '.join(missing)}")

        # 按逗号拆分收件人，去空白、去空项
        to = [addr.strip() for addr in to_raw.split(",") if addr.strip()]
        return cls(host=host, port=port, user=user, password=password, to=to)


def build_message(cfg: SMTPConfig, subject: str, html_body: str, text_body: str) -> MIMEMultipart:
    """构建 HTML + 纯文本双正文的 MIME 邮件消息（不含发送逻辑，便于测试）。

    Parameters
    ----------
    cfg : SMTPConfig
        SMTP 配置（From/To 取 cfg.user / cfg.to）。
    subject : str
        邮件主题（中文自动 UTF-8 编码）。
    html_body : str
        HTML 格式正文。
    text_body : str
        纯文本格式正文。

    Returns
    -------
    MIMEMultipart
        可单独测试编码正确性的 MIME 对象。
    """
    msg = MIMEMultipart("alternative")
    from_addr: str = formataddr((str(Header(cfg.user, "utf-8")), cfg.user))
    msg["From"] = from_addr
    msg["To"] = ", ".join(cfg.to)
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["Date"] = str(formatdate(localtime=True))

    # 顺序重要：纯文本在前，HTML 在后（兼容客户端取最后一部分）
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def send_email(
    cfg: SMTPConfig,
    subject: str,
    html_body: str,
    text_body: str,
    to: list[str] | None = None,
) -> None:
    """发送 HTML + 纯文本双正文邮件。

    Parameters
    ----------
    cfg : SMTPConfig
        SMTP 配置。
    subject : str
        邮件主题。
    html_body : str
        HTML 正文。
    text_body : str
        纯文本正文。
    to : list of str or None
        覆盖收件人（默认用 cfg.to）。

    Raises
    ------
    EmailError
        无收件人、SMTP 连接/登录/发送失败。

    Notes
    -----
    端口策略：465 走 SSL（SMTP_SSL），其余端口（如 587）用 STARTTLS 升级连接。
    """
    recipients = to or cfg.to
    if not recipients:
        raise EmailError("没有收件人，请设置 SMTP_TO 或传入 to 参数。")

    msg = build_message(cfg, subject, html_body, text_body)

    try:
        if cfg.port == 465:
            # 465 端口：全程 SSL 加密
            with smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=30) as server:
                _auth_and_send(server, cfg, recipients, msg)
        else:
            # 587 等端口：先明文握手，再 starttls 升级为加密通道
            with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as server:
                server.starttls()
                _auth_and_send(server, cfg, recipients, msg)
    except EmailError:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一包装为 EmailError
        raise EmailError(f"邮件发送失败: {exc}") from exc


def _auth_and_send(server: smtplib.SMTP, cfg: SMTPConfig, recipients: list[str], msg: MIMEMultipart) -> None:
    """登录 SMTP 服务器并发送邮件（连接已建立，按端口策略加密）。

    Parameters
    ----------
    server : smtplib.SMTP
        已建立（并已加密）的 SMTP 连接。
    cfg : SMTPConfig
        SMTP 配置（用于 user / password 登录）。
    recipients : list of str
        收件人列表。
    msg : MIMEMultipart
        已构造好的 MIME 邮件消息。
    """
    server.login(cfg.user, cfg.password)
    server.sendmail(cfg.user, recipients, msg.as_string())
