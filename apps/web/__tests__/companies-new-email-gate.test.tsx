import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CreateCompanyPage from "@/app/(app)/companies/new/page";

/**
 * Regression coverage for the ForgeX Product Audit's P1 finding:
 * "New Company enforces the email-verification requirement only after
 * a full form submit, shown as one small line below the fold." The
 * fix surfaces the same, already-known (`user.is_email_verified`)
 * requirement immediately instead of after a wasted form fill-out.
 */

const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  accessToken: "token" as string | null,
  user: {
    id: "u1",
    email: "founder@example.com",
    full_name: "Founder",
    role: "owner" as const,
    is_active: true,
    is_email_verified: true,
    created_at: "2026-01-01T00:00:00Z",
  } as null | Record<string, unknown>,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

describe("CreateCompanyPage", () => {
  afterEach(() => {
    pushMock.mockClear();
    authState.status = "authenticated";
    authState.user = {
      id: "u1",
      email: "founder@example.com",
      full_name: "Founder",
      role: "owner",
      is_active: true,
      is_email_verified: true,
      created_at: "2026-01-01T00:00:00Z",
    };
  });

  it("blocks the form up front for an unverified account instead of letting them fill it out", () => {
    authState.user = { ...(authState.user as Record<string, unknown>), is_email_verified: false };
    render(<CreateCompanyPage />);
    expect(screen.getByText(/please verify your email address before continuing/i)).toBeTruthy();
    expect(screen.queryByLabelText(/company name/i)).toBeNull();
  });

  it("tells the buyer which inbox to check", () => {
    authState.user = { ...(authState.user as Record<string, unknown>), is_email_verified: false };
    render(<CreateCompanyPage />);
    expect(screen.getByText(/founder@example\.com/)).toBeTruthy();
  });

  it("offers a way back to the Dashboard instead of a dead end", () => {
    authState.user = { ...(authState.user as Record<string, unknown>), is_email_verified: false };
    render(<CreateCompanyPage />);
    expect(screen.getByRole("link", { name: /back to dashboard/i }).getAttribute("href")).toBe("/dashboard");
  });

  it("renders the real form once the account is verified", () => {
    render(<CreateCompanyPage />);
    expect(screen.getByLabelText(/company name/i)).toBeTruthy();
    expect(screen.queryByText(/please verify your email address before continuing/i)).toBeNull();
  });

  it("P1 #10 (ForgeX Product Audit): explains what the form is for instead of dropping straight into fields with no stated purpose", () => {
    render(<CreateCompanyPage />);
    expect(screen.getByText(/Buyers discover you through ForgeX Consult/)).toBeTruthy();
  });

  it("renders nothing while unauthenticated — the redirect effect handles navigation", () => {
    authState.status = "unauthenticated";
    authState.user = null;
    const { container } = render(<CreateCompanyPage />);
    expect(container.textContent).toBe("");
  });
});
