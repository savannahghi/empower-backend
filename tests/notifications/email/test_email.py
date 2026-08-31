"""Test emailing."""
from unittest.mock import patch

from django.test import TestCase, override_settings

from sil_advantage.notifications.email import send_email

MOCK_ROOT = "sil_advantage.notifications.email."


@override_settings(
    DEFAULT_FROM_EMAIL="advantage-do-not-reply@slade.com",
)
class EmailingTest(TestCase):
    """Test emailing."""

    @override_settings(ENVIRONMENT="prod")
    @patch(MOCK_ROOT + "EmailMultiAlternatives")
    @patch(MOCK_ROOT + "loader")
    def test_send_email_on_prod(self, mock_loader, mock_email_alts):
        """Test sending an email on production."""
        mock_loader.get_template.return_value.render.return_value = (
            "New phone, who dis?"
        )
        send_email(
            "SladeAdvantage Daily Digest",
            ["stephen@example.com"],
            "daily_report_email.mjml",
            "daily_report_email.mjml",
            {},
            "Oregon Healthcare",
        )
        mock_email_alts.assert_called_once_with(
            subject="SladeAdvantage Daily Digest",
            body="New phone, who dis?",
            from_email="Oregon Healthcare <advantage-do-not-reply@slade.com>",
            to=["stephen@example.com"],
            attachments=None,
            cc=None,
            bcc=None,
            headers=None,
        )

    @override_settings(ENVIRONMENT="test")
    @patch(MOCK_ROOT + "EmailMultiAlternatives")
    @patch(MOCK_ROOT + "loader")
    def test_append_prefix_on_test(self, mock_loader, mock_email_alts):
        """Test appending the [TEST] prefix on test."""
        mock_loader.get_template.return_value.render.return_value = (
            "New phone, who dis?"
        )
        send_email(
            "SladeAdvantage Daily Digest",
            ["stephen@example.com"],
            "daily_report_email.mjml",
            "daily_report_email.mjml",
            {},
            "Oregon Healthcare",
        )
        mock_email_alts.assert_called_once_with(
            subject="SladeAdvantage Daily Digest [TEST]",
            body="New phone, who dis?",
            from_email="Oregon Healthcare <advantage-do-not-reply@slade.com>",
            to=["stephen@example.com"],
            attachments=None,
            cc=None,
            bcc=None,
            headers=None,
        )
