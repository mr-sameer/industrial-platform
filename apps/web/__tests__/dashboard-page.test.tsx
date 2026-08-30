import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";

/**
 * Regression coverage for the ForgeX Product Audit's P0 #3: the
 * first-session Dashboard was a literal, self-labeled placeholder
 * ("Real dashboard content arrives with the first business-feature
 * module") shown immediately after registering — a brand-new user's
 * very first authenticated screen. Replaced with a small, real welcome
 * view; these tests cover that it actually renders real user data and
 * a path into the two features that exist today, not that it grew into
 * a full dashboard (it deliberately didn't).
 */

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  user: {
    id: "u1",
    email: "audit.tester.fx@example.com",
    full_name: "Audit Tester",
    role: "viewer" as const,
    is_active: true,
    is_email_verified: true,
    created_at: "2026-01-01T00:00:00Z",
  } as null | Record<string, unknown>,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

describe("DashboardPage", () => {
  afterEach(() => {
    pushMock.mockClear();
    authState.status = "authenticated";
    authState.user = {
      id: "u1",
      email: "audit.tester.fx@example.com",
      full_name: "Audit Tester",
      role: "viewer",
      is_active: true,
      is_email_verified: true,
      created_at: "2026-01-01T00:00:00Z",
    };
  });

  it("welcomes the real signed-in user by name, email, and role — not placeholder debug text", () => {
    render(<DashboardPage />);
    expect(screen.getByText("Welcome, Audit Tester")).toBeTruthy();
    expect(screen.getByText(/audit\.tester\.fx@example\.com/)).toBeTruthy();
    expect(screen.getByText(/viewer/)).toBeTruthy();
  });

  it("links into the two features that actually exist today — Consult and Companies", () => {
    render(<DashboardPage />);
    expect(screen.getByRole("link", { name: /Ask ForgeX/ }).getAttribute("href")).toBe("/consult");
    expect(screen.getByRole("link", { name: /Your companies/ }).getAttribute("href")).toBe("/companies");
  });

  it("surfaces the email-verification requirement when the account isn't verified yet", () => {
    authState.user = { ...(authState.user as Record<string, unknown>), is_email_verified: false };
    render(<DashboardPage />);
    expect(screen.getByText(/email isn't verified yet/i)).toBeTruthy();
  });

  it("does not show the verification notice once the account is verified", () => {
    render(<DashboardPage />);
    expect(screen.queryByText(/email isn't verified yet/i)).toBeNull();
  });

  it("renders nothing while unauthenticated — the redirect effect handles navigation", () => {
    authState.status = "unauthenticated";
    authState.user = null;
    const { container } = render(<DashboardPage />);
    expect(container.textContent).toBe("");
  });
});
