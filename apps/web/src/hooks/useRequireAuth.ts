"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/contexts/AuthContext";

/**
 * Shared client-side auth guard — extracted from the pattern first used
 * in src/app/dashboard/page.tsx (Module 2) so every Module 3A company
 * page doesn't reimplement the same loading/redirect logic. Returns the
 * same `status`/`user`/`accessToken` a caller needs; the caller is
 * responsible for rendering nothing (`return null`) while
 * `status !== "authenticated"`, since the redirect effect handles
 * navigation asynchronously.
 */
export function useRequireAuth(redirectTo: string) {
  const auth = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (auth.status === "unauthenticated") {
      router.push(`/login?next=${encodeURIComponent(redirectTo)}`);
    }
  }, [auth.status, redirectTo, router]);

  return auth;
}
