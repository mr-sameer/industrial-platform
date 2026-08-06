"""
Email sending abstraction. Module 2.5 ships only a logging implementation
— no SMTP/transactional-email provider has been chosen for this platform
yet, and wiring one up is an infrastructure decision, not an auth-hardening
one. The interface here is the seam a real provider (SES, Postmark,
Resend, etc.) plugs into without touching call sites in verification_service
or password_reset_service. See docs/adr/0019-email-verification-and-password-reset.md.
"""

from typing import Protocol

from app.core.logging import get_logger

logger = get_logger(__name__)


class EmailSender(Protocol):
    async def send(self, *, to: str, subject: str, html_body: str) -> None: ...


class LoggingEmailSender:
    """Development/test implementation — logs the email instead of sending it."""

    async def send(self, *, to: str, subject: str, html_body: str) -> None:
        logger.info("email_send_stub", to=to, subject=subject, body_length=len(html_body))


_sender: EmailSender = LoggingEmailSender()


def get_email_sender() -> EmailSender:
    return _sender


def render_verification_email(*, full_name: str, verification_url: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
  <body style="font-family: -apple-system, Helvetica, Arial, sans-serif; background:#f6f7f8; padding:32px;">
    <table role="presentation" style="max-width:480px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden;">
      <tr><td style="background:#1a3c34; padding:24px; color:#fff; font-size:18px;">Industrial Intelligence Platform</td></tr>
      <tr><td style="padding:24px;">
        <p>Hi {full_name},</p>
        <p>Please confirm your email address to finish setting up your account.</p>
        <p style="text-align:center; margin:32px 0;">
          <a href="{verification_url}" style="background:#1a3c34; color:#fff; padding:12px 24px; border-radius:6px; text-decoration:none;">Verify email</a>
        </p>
        <p style="color:#666; font-size:13px;">This link expires in 24 hours. If you didn't create this account, you can ignore this email.</p>
      </td></tr>
    </table>
  </body>
</html>"""


def render_password_reset_email(*, full_name: str, reset_url: str) -> str:
    return f"""\
<!DOCTYPE html>
<html>
  <body style="font-family: -apple-system, Helvetica, Arial, sans-serif; background:#f6f7f8; padding:32px;">
    <table role="presentation" style="max-width:480px; margin:0 auto; background:#fff; border-radius:8px; overflow:hidden;">
      <tr><td style="background:#1a3c34; padding:24px; color:#fff; font-size:18px;">Industrial Intelligence Platform</td></tr>
      <tr><td style="padding:24px;">
        <p>Hi {full_name},</p>
        <p>We received a request to reset your password. If this wasn't you, you can safely ignore this email — your password will not change.</p>
        <p style="text-align:center; margin:32px 0;">
          <a href="{reset_url}" style="background:#1a3c34; color:#fff; padding:12px 24px; border-radius:6px; text-decoration:none;">Reset password</a>
        </p>
        <p style="color:#666; font-size:13px;">This link expires in 1 hour and can only be used once.</p>
      </td></tr>
    </table>
  </body>
</html>"""
