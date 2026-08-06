# Threat Model — Auth System (Module 2.5)

A lightweight STRIDE-style pass over the auth system as it exists after
Module 2.5. Scope: authentication, session management, and the
account-recovery flows. Out of scope: infrastructure-level threats
(host compromise, DB exfiltration via SQLi elsewhere in the platform —
covered generically by parameterized queries via SQLAlchemy throughout)
and business-logic threats for features that don't exist yet.

## Assets
- User credentials (passwords, password hashes)
- Access and refresh tokens
- Session metadata (IP, device, browser)
- Audit log (who did what, when, from where)
- Email addresses (PII, and the account-recovery channel)

## Actors
- Legitimate user (web or mobile)
- Attacker with network access only (no credentials)
- Attacker with a stolen access token (short-lived exposure window)
- Attacker with a stolen refresh token (longer exposure window — the higher-value target)
- Malicious/compromised client-side script (web XSS scenario)

## Threats and mitigations

| # | Threat (STRIDE category) | Mitigation | Residual risk |
|---|---|---|---|
| 1 | Credential stuffing / brute force (Spoofing) | Per-IP rate limiting + progressive per-account lockout | Distributed low-and-slow attacks below both thresholds are still possible; no CAPTCHA fallback |
| 2 | Password database compromise → offline cracking (Info Disclosure) | Argon2id hashing (memory-hard, GPU-resistant) | Any hash can theoretically be cracked given enough compute; strength rules + blacklist reduce the weak-password tail |
| 3 | Stolen refresh token replayed by attacker (Spoofing / Elevation) | Rotation + reuse detection revokes the whole session on replay | Detection is *after-the-fact* — the attacker's single use of the stolen token before the legitimate user's next refresh still succeeds. True real-time prevention would need binding tokens to a device fingerprint, not done here. |
| 4 | XSS on the web app exfiltrating tokens (Info Disclosure) | Refresh token in httpOnly cookie (unreachable by JS); access token in memory only (not localStorage) | An XSS payload can still call authenticated APIs *as the user* for as long as the page is open (via the in-memory access token / ambient session), and can still trigger actions through the BFF routes. Full XSS mitigation is a CSP + input-sanitization concern outside this module's scope — the CSP shipped here is a floor, not a complete answer, since the web app currently has no user-generated content surfaces to sanitize yet. |
| 5 | CSRF against cookie-authenticated BFF routes (Spoofing) | `SameSite=Lax` cookie + Origin-header check on refresh/logout | Lax + Origin check together are strong for standard browsers; embedded webviews with nonstandard cookie/fetch behavior are a known softer spot, not independently verified here |
| 6 | Account takeover via password reset (Elevation) | Reset requires proof of email-inbox access (token delivered to that address); token is single-use, 1h-expiring; all sessions revoked on reset | **Currently undermined by ADR-0019**: no real email provider is wired up, so in any non-local environment, reset tokens don't actually reach the user's inbox yet. Wiring up a real provider is a prerequisite for this mitigation to hold in production. |
| 7 | Email enumeration via register/login/forgot-password (Info Disclosure) | All three endpoints give identical responses regardless of account existence | None known for these three endpoints specifically |
| 8 | Session fixation / hijacking via IP/device metadata (Spoofing) | IP/device/browser are **cosmetic only**, never used for authorization decisions | None — this is deliberate; treating spoofable metadata as a security control would be worse than not using it |
| 9 | Denial of service via registration spam | Per-IP rate limit on `/register` | A botnet with many IPs can still create many accounts; no email-verification-gate on registration itself (verification is required for *future* features, not registration — see ADR-0015) |
| 10 | Audit log tampering (Repudiation) | Audit log is a normal DB table with standard access controls | No append-only/tamper-evident guarantee (e.g. hash chaining) — an attacker with DB write access could alter or delete audit rows. Acceptable at this stage; revisit if this platform's compliance requirements demand tamper-evidence. |
| 11 | Timing attacks distinguishing valid/invalid emails at login | Both the "unknown email" and "wrong password" paths now run a real Argon2id verification before failing — the unknown-email path verifies against a fixed dummy hash instead of short-circuiting. Verified by `tests/test_auth.py::test_login_with_unknown_email_still_calls_verify_password`. | Residual: verification *cost* is equalized, but other micro-timing differences (e.g. the extra DB query on the known-email path) are not independently measured or bounded. Found and fixed while writing this document — not caught by earlier code review. |

## Notable non-goals (explicitly out of scope for this module)
- Multi-factor authentication (not requested; no scaffolding added)
- Device-binding / token-to-device cryptographic attestation
- IP-reputation or geo-velocity anomaly detection
- Tamper-evident audit logging
