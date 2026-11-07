import pytest
from unittest.mock import MagicMock, patch
from app.business.password_reset_email import send_reset_email


def test_send_reset_email_missing_configuration(app):
    with app.app_context():
        app.config["MAIL_HOST"] = None
        app.config["MAIL_USERNAME"] = None
        app.config["MAIL_PASSWORD"] = None
        app.config["MAIL_FROM"] = None

        with pytest.raises(RuntimeError, match="Password reset email is not configured"):
            send_reset_email("user@example.com", "http://localhost/reset-token")


def test_send_reset_email_tls_enabled(app):
    with app.app_context():
        app.config["MAIL_HOST"] = "smtp.example.com"
        app.config["MAIL_PORT"] = 587
        app.config["MAIL_USERNAME"] = "mailer@example.com"
        app.config["MAIL_PASSWORD"] = "SecretMailPass"
        app.config["MAIL_FROM"] = "noreply@example.com"
        app.config["MAIL_USE_TLS"] = True

        mock_smtp = MagicMock()
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        with patch("smtplib.SMTP", mock_smtp):
            send_reset_email("testuser@example.com", "http://localhost/reset/abc123token")

        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
        assert mock_server.ehlo.call_count == 2
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("mailer@example.com", "SecretMailPass")
        assert mock_server.send_message.call_count == 1
        sent_msg = mock_server.send_message.call_args[0][0]
        assert sent_msg["Subject"] == "Reset your Electronics Store password"
        assert sent_msg["From"] == "noreply@example.com"
        assert sent_msg["To"] == "testuser@example.com"
        assert "http://localhost/reset/abc123token" in sent_msg.get_content()


def test_send_reset_email_tls_disabled(app):
    with app.app_context():
        app.config["MAIL_HOST"] = "smtp.internal"
        app.config["MAIL_PORT"] = 25
        app.config["MAIL_USERNAME"] = "internal@example.com"
        app.config["MAIL_PASSWORD"] = "InternalPass"
        app.config["MAIL_FROM"] = "internal@example.com"
        app.config["MAIL_USE_TLS"] = False

        mock_smtp = MagicMock()
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        with patch("smtplib.SMTP", mock_smtp):
            send_reset_email("testuser2@example.com", "http://localhost/reset/token456")

        mock_server.starttls.assert_not_called()
        assert mock_server.ehlo.call_count == 1
        mock_server.login.assert_called_once_with("internal@example.com", "InternalPass")
        mock_server.send_message.assert_called_once()

