# 0019 — Email Sending: Stub Implementation Behind a Protocol Seam

## Status
Accepted

## Context
Email verification (ADR-0015) and password reset (ADR-0016) both need to
send emails. No transactional-email provider (SES, Postmark, Resend,
SendGrid, etc.) has been chosen for this platform, and picking one is an
infrastructure/vendor decision independent of the auth-hardening work in
this module.

## Decision
`app.services.email_service.EmailSender` is a `Protocol` with a single
`send(to, subject, html_body)` method. `LoggingEmailSender` is the only
implementation shipped in Module 2.5 — it logs the email via structlog
(`email_send_stub` event) instead of sending it. `render_verification_email`
and `render_password_reset_email` produce real, responsive HTML (inline
styles, table-based layout for email-client compatibility, IBM-Plex-free
system font stack) so the templates themselves are production-ready even
though delivery isn't wired up.

## Alternatives considered
- **Pick a provider now (e.g. SES via boto3)**: rejected for this module
  — would add a cloud-provider dependency and credentials-management
  concern to what's meant to be an auth-hardening pass, and the "right"
  provider depends on decisions (region, existing AWS/GCP footprint)
  that haven't been made for this platform yet.

## Consequences
- **In any environment other than local dev, nobody actually receives
  verification or password-reset emails yet.** This is the single most
  important deployment blocker this module introduces — flagged clearly
  in Phase 15's Production Readiness Review and the README's Module 3
  checklist. Do not consider email-dependent flows (verification,
  password reset) production-ready until a real `EmailSender`
  implementation replaces `LoggingEmailSender` (swap in
  `app.services.email_service.get_email_sender`'s returned instance —
  every call site is already written against the `EmailSender` protocol,
  not a concrete class).
- Tests deliberately don't assert anything about email delivery — they
  extract tokens directly from the database (see
  `tests/test_email_verification.py`'s and
  `tests/test_password_reset.py`'s module docstrings), since token
  issuance/consumption logic is identical regardless of delivery
  mechanism.
