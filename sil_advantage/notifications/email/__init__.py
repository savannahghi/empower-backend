"""Email sending utility."""
from typing import Any, Optional

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import loader


def send_email(
    subject: str,
    to: list[str],
    html_temp: str,
    plain_text: str,
    context_obj: dict[str, Any],
    org_name: str,
    attachments: Optional[list] = None,
    cc: Optional[list[str]] = None,
    headers: Optional[dict[str, str]] = None,
    bcc: Optional[list[str]] = None,
) -> None:
    """Send an email."""
    if settings.ENVIRONMENT.lower() != "prod":  # type: ignore
        subject += " [TEST]"
    plain_text_content = loader.get_template(plain_text).render(context_obj)
    html_content = loader.get_template(html_temp).render(context_obj)
    sender = "{} <{}>".format(org_name, settings.DEFAULT_FROM_EMAIL)  # type: ignore
    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain_text_content,
        from_email=sender,
        to=to,
        attachments=attachments,
        cc=cc,
        headers=headers,
        bcc=bcc,
    )
    msg.attach_alternative(html_content, "text/html")
    msg.send(fail_silently=False)
