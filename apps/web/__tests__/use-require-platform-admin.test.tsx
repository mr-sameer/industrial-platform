import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useRequirePlatformAdmin } from "@/hooks/useRequirePlatformAdmin";

/**
 * Phase 2B-1: the platform-admin route guard that will gate the admin
 * verification queue page (not yet built — see useRequirePlatformAdmin's
 * own docstring). Tested directly via renderHook rather than through a
 * consuming page, since no page uses it yet in this phase. Mirrors
 * __tests__/dashboard-page.test.tsx's hoisted-mock style for
 * @/contexts/AuthContext.
 */
const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  accessToken: "token-abc" as string | null,
  user: null as null | Record<string, unknown>,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

describe("useRequirePlatformAdmin", () => {
  afterEach(() => {
    pushMock.mockClear();
    authState.status = "authenticated";
    authState.accessToken = "token-abc";
    authState.user = null;
  });

  it("allows a platform admin through without redirecting", () => {
    authState.status = "authenticated";
    authState.user = { id: "u1", role: "admin" };

    const { result } = renderHook(() => useRequirePlatformAdmin("/admin/verification"));

    expect(pushMock).not.toHaveBeenCalled();
    expect(result.current.status).toBe("authenticated");
    expect(result.current.user).toEqual({ id: "u1", role: "admin" });
  });

  it("redirects an authenticated non-admin (viewer) to /dashboard", () => {
    authState.status = "authenticated";
    authState.user = { id: "u2", role: "viewer" };

    renderHook(() => useRequirePlatformAdmin("/admin/verification"));

    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });

  it("redirects an authenticated non-admin (analyst) to /dashboard", () => {
    authState.status = "authenticated";
    authState.user = { id: "u3", role: "analyst" };

    renderHook(() => useRequirePlatformAdmin("/admin/verification"));

    expect(pushMock).toHaveBeenCalledWith("/dashboard");
  });

  it("defers to useRequireAuth's own /login redirect when unauthenticated, without also redirecting to /dashboard", () => {
    authState.status = "unauthenticated";
    authState.user = null;

    renderHook(() => useRequirePlatformAdmin("/admin/verification"));

    expect(pushMock).toHaveBeenCalledWith("/login?next=%2Fadmin%2Fverification");
    expect(pushMock).not.toHaveBeenCalledWith("/dashboard");
    expect(pushMock).toHaveBeenCalledTimes(1);
  });

  it("does not redirect while auth status is still loading", () => {
    authState.status = "loading";
    authState.user = null;

    renderHook(() => useRequirePlatformAdmin("/admin/verification"));

    expect(pushMock).not.toHaveBeenCalled();
  });
});
