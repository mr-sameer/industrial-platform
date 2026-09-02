"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useRequireAuth } from "@/hooks/useRequireAuth";

/**
 * Platform-admin route guard — Phase 2B-1. Wraps useRequireAuth (so
 * "not signed in at all" is still handled exactly the way every other
 * page handles it — same redirect-to-/login-with-next behavior, same
 * "loading" status while the auth bootstrap settles) rather than
 * introducing a second, parallel authentication check. Adds exactly
 * one more condition on top: an authenticated user whose platform
 * `role` (see packages/shared-types/src/auth.ts's `Role` — "admin" |
 * "analyst" | "viewer", already returned by GET /auth/me and already
 * present on useAuth().user today) isn't "admin" is redirected to
 * /dashboard — the same safe landing page useRequireAuth's own
 * unauthenticated path effectively lands non-admins on, since they're
 * still a real signed-in user, just not authorized for this route.
 *
 * Deliberately does NOT gate anything at the CompanyRole layer (see
 * app/core/company_authorization.py's distinction, mirrored here) —
 * this checks the platform-wide Role only, matching the backend's own
 * RequireAdmin (require_role(Role.ADMIN)) used by
 * GET /companies/documents/pending and the document review endpoint.
 */
export function useRequirePlatformAdmin(redirectTo: string) {
  const auth = useRequireAuth(redirectTo);
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "authenticated" && auth.user?.role !== "admin") {
      router.push("/dashboard");
    }
  }, [auth.status, auth.user, router]);

  return auth;
}
