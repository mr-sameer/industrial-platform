/**
 * Auth contracts, mirroring app/schemas/auth.py and app/models/user.py.
 * The web app never sends/receives these directly against the FastAPI
 * service — it goes through the BFF route handlers under
 * apps/web/src/app/api/auth/ — but the shapes are identical either way,
 * so one set of types serves both.
 */

export type Role = "admin" | "analyst" | "viewer";

export interface UserPublic {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  is_email_verified: boolean;
  created_at: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  device_name?: string;
}

export interface LoginRequest {
  email: string;
  password: string;
  device_name?: string;
}

/** The full shape the FastAPI service returns. Only used server-side (BFF route handlers). */
export interface AuthTokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in_minutes: number;
  user: UserPublic;
}

/** What the browser actually receives from apps/web's own /api/auth/* routes — no refresh_token. */
export interface ClientSession {
  access_token: string;
  expires_in_minutes: number;
  user: UserPublic;
}

/**
 * One row from GET /auth/sessions — "your active sessions/devices" (see
 * docs/adr/0014-refresh-token-and-session-model.md). `is_current` is
 * computed server-side by comparing IP + User-Agent to the requesting
 * client; it's a display hint only, not a security boundary.
 */
export interface SessionPublic {
  id: string;
  device_name: string | null;
  browser: string | null;
  platform: string | null;
  ip_address: string | null;
  created_at: string;
  last_active_at: string;
  is_current: boolean;
}

/** Mirrors app.schemas.auth.ForgotPasswordRequest exactly. */
export interface ForgotPasswordRequest {
  email: string;
}

/** Mirrors app.schemas.auth.ResetPasswordRequest exactly. */
export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

/** Mirrors app.schemas.auth.VerifyEmailRequest exactly. */
export interface VerifyEmailRequest {
  token: string;
}
