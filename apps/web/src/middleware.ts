import { NextResponse, type NextRequest } from "next/server";

/**
 * Lightweight, non-cryptographic route gate: redirects to /login if the
 * httpOnly refresh-token cookie is absent. This is a UX convenience, NOT
 * the security boundary — the API independently verifies the access
 * token on every request (see app/core/dependencies.get_current_user).
 * A present-but-expired cookie still redirects a real user through the
 * normal AuthContext bootstrap-then-redirect flow rather than here.
 */
const PROTECTED_PREFIXES = ["/dashboard"];
const REFRESH_TOKEN_COOKIE_NAME = process.env.REFRESH_TOKEN_COOKIE_NAME ?? "refresh_token";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix));
  if (!isProtected) return NextResponse.next();

  const hasSessionCookie = request.cookies.has(REFRESH_TOKEN_COOKIE_NAME);
  if (!hasSessionCookie) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/dashboard/:path*"],
};
