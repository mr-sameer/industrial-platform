import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NavLinks } from "@/components/shell/Sidebar";

/**
 * P0 #5 (Buyer UX Audit): after registering/logging in, the authenticated
 * shell's nav was Dashboard / Companies / Search with no path back to
 * Consult — the core buyer workflow. See components/shell/Sidebar.tsx.
 */
vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("Sidebar nav links", () => {
  it("includes a Consult entry point alongside Dashboard/Companies/Search", () => {
    render(<NavLinks />);
    const link = screen.getByText("Ask ForgeX").closest("a");
    expect(link).toBeTruthy();
    expect(link?.getAttribute("href")).toBe("/consult");
    expect(screen.getByText("Dashboard")).toBeTruthy();
    expect(screen.getByText("Companies")).toBeTruthy();
    expect(screen.getByText("Search")).toBeTruthy();
  });
});
