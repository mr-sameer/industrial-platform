import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NavLinks } from "@/components/shell/Sidebar";

/**
 * Phase 2B-1: the Verification queue nav entry (-> /admin/verification,
 * the admin queue page itself is Phase 2B-2, not yet built) must be
 * visible only to platform-Role.ADMIN users — matching the backend's
 * own RequireAdmin gate on GET /companies/documents/pending exactly.
 * NavLinks is shared by both Sidebar (desktop) and MobileNav (drawer) —
 * testing it directly, as sidebar-consult-nav.test.tsx already does,
 * covers both automatically without duplicating this check per-component.
 */
vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

const authState = vi.hoisted(() => ({
  user: null as null | { id: string; role: string },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

describe("Sidebar nav links — admin-only Verification queue entry", () => {
  it("shows Verification queue for an admin user", () => {
    authState.user = { id: "u1", role: "admin" };
    render(<NavLinks />);

    const link = screen.getByText("Verification queue").closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("/admin/verification");
  });

  it("hides Verification queue for a viewer", () => {
    authState.user = { id: "u2", role: "viewer" };
    render(<NavLinks />);

    expect(screen.queryByText("Verification queue")).toBeNull();
  });

  it("hides Verification queue for an analyst", () => {
    authState.user = { id: "u3", role: "analyst" };
    render(<NavLinks />);

    expect(screen.queryByText("Verification queue")).toBeNull();
  });

  it("hides Verification queue when unauthenticated (no user)", () => {
    authState.user = null;
    render(<NavLinks />);

    expect(screen.queryByText("Verification queue")).toBeNull();
  });

  it("preserves every existing nav item alongside the admin-only entry", () => {
    authState.user = { id: "u1", role: "admin" };
    render(<NavLinks />);

    expect(screen.getByText("Ask ForgeX")).toBeTruthy();
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(screen.getByText("Companies")).toBeTruthy();
    expect(screen.getByText("Search")).toBeTruthy();
    expect(screen.getByText("Verification queue")).toBeTruthy();
  });
});
