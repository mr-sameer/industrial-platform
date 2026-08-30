import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import CompanyListPage from "@/app/(app)/companies/page";

/**
 * Regression coverage for the ForgeX Product Audit's P1 #10 finding:
 * "Companies list ... functionally correct but extremely bare — no
 * explanatory copy." The empty state previously said nothing about why
 * a company matters; this covers that the added line actually renders
 * once the (empty) company list loads.
 */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    status: "authenticated",
    accessToken: "token",
    user: {
      id: "u1",
      email: "founder@example.com",
      full_name: "Founder",
      role: "owner",
      is_active: true,
      is_email_verified: true,
      created_at: "2026-01-01T00:00:00Z",
    },
  }),
}));

vi.mock("@/lib/companies", () => ({
  listMyCompanies: vi.fn().mockResolvedValue({
    success: true,
    data: [],
    meta: { requestId: "x", timestamp: "now" },
  }),
}));

describe("CompanyListPage — empty state", () => {
  it("explains what a company unlocks instead of just offering an empty card and a button", async () => {
    render(<CompanyListPage />);
    await waitFor(() => expect(screen.getByText(/not part of any company yet/)).toBeTruthy());
    expect(screen.getByText(/Buyers find and evaluate companies through ForgeX Consult/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /create your first company/i }).getAttribute("href")).toBe(
      "/companies/new"
    );
  });
});
