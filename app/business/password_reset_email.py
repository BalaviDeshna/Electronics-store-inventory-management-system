import smtplib
from email.message import EmailMessage

from flask import current_app


def send_reset_email(recipient, reset_url):
    cfg = current_app.config
    required = [
        cfg.get("MAIL_HOST"),
        cfg.get("MAIL_USERNAME"),
        cfg.get("MAIL_PASSWORD"),
        cfg.get("MAIL_FROM"),
    ]

    if not all(required):
        raise RuntimeError("Password reset email is not configured")

    msg = EmailMessage()
    msg["Subject"] = "Reset your Electronics Store password"
    msg["From"] = cfg["MAIL_FROM"]
    msg["To"] = recipient
    msg.set_content(
        "A password reset was requested. Use this link within 30 minutes:\n"
        f"{reset_url}\n\nIf you did not request this, ignore this email."
    )

    with smtplib.SMTP(
        cfg["MAIL_HOST"], cfg["MAIL_PORT"], timeout=15
    ) as server:
        server.ehlo()

        if cfg.get("MAIL_USE_TLS", True):
            server.starttls()
            server.ehlo()

        server.login(cfg["MAIL_USERNAME"], cfg["MAIL_PASSWORD"])
        server.send_message(msg)