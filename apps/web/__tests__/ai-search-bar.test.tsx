import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AISearchBar } from "@/components/home/AISearchBar";
import { searchCompanies } from "@/lib/companies";

/**
 * Covers P0 #1 of the audit fix: the homepage's "Ask ForgeX" bar
 * previously routed every submission to the old company-*name*-only
 * search (GET /companies/search via /discover), which meant its own
 * rotating placeholder examples ("Need 5,000 hydraulic cylinders")
 * never returned anything for a real visitor. Enter/Search must now
 * hand the query to the real Consult requirement flow instead — the
 * live as-you-type company-name dropdown (a separate, honest, still-
 * working feature) must keep working unchanged.
 */

const pushMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/companies", () => ({
  searchCompanies: vi.fn(),
}));

// The search bar coalesces its own state update to the next animation
// frame (see AISearchBar.tsx's handleQueryChange) so a burst of scripted
// keystrokes can't trip React's "Maximum update depth exceeded" — a real
// browser paints between `fireEvent.change` and that frame, but jsdom
// doesn't, so a test that depends on the resulting state (here: the
// loading spinner settling back to the Search button) must explicitly
// flush one frame itself.
async function flushAnimationFrame() {
  await act(async () => {
    await new Promise((resolve) => requestAnimationFrame(resolve));
  });
}

const emptyCompanyPage = {
  success: true as const,
  data: { items: [], total: 0, page: 1, page_size: 6, total_pages: 1 },
  meta: { requestId: "x", timestamp: "now" },
};

describe("AISearchBar", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    pushMock.mockClear();
  });

  it("routes a submitted query into the real Consult flow on Enter, not the old company-name-only search", () => {
    vi.mocked(searchCompanies).mockResolvedValue(emptyCompanyPage);
    render(<AISearchBar />);

    const input = screen.getByLabelText("Ask ForgeX AI");
    fireEvent.change(input, { target: { value: "Need 500 room heaters" } });
    fireEvent.keyDown(input, { key: "Enter" });

    expect(pushMock).toHaveBeenCalledWith("/consult?q=Need%20500%20room%20heaters");
    expect(pushMock).not.toHaveBeenCalledWith(expect.stringContaining("/discover"));
  });

  it("routes a submitted query into Consult when the Search button is clicked", async () => {
    vi.mocked(searchCompanies).mockResolvedValue(emptyCompanyPage);
    render(<AISearchBar />);

    const input = screen.getByLabelText("Ask ForgeX AI");
    fireEvent.change(input, { target: { value: "Find a CNC manufacturer in Germany" } });
    await flushAnimationFrame();
    // The debounced live-search effect briefly swaps the Search button
    // for a loading spinner (same element the button occupies) — wait
    // for it to settle back to the real button before clicking it.
    await waitFor(() => expect(screen.getByLabelText("Search")).toBeTruthy());
    fireEvent.click(screen.getByLabelText("Search"));

    expect(pushMock).toHaveBeenCalledWith("/consult?q=Find%20a%20CNC%20manufacturer%20in%20Germany");
  });

  it("does not submit on Enter for a query shorter than 2 characters", () => {
    render(<AISearchBar />);
    const input = screen.getByLabelText("Ask ForgeX AI");
    fireEvent.change(input, { target: { value: "a" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(pushMock).not.toHaveBeenCalled();
  });

  /**
   * ForgeX Product Audit P1 #1: the composer is now a growing textarea,
   * not a single-line input — Shift+Enter must insert a real newline for
   * a long, natural multi-line procurement requirement instead of
   * submitting early.
   */
  it("does not submit on Shift+Enter — that inserts a newline instead", () => {
    render(<AISearchBar />);
    const input = screen.getByLabelText("Ask ForgeX AI");
    fireEvent.change(input, { target: { value: "Need 5,000 hydraulic cylinders" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("still shows live company-name matches while typing — unaffected by the Consult routing change", async () => {
    vi.mocked(searchCompanies).mockResolvedValue({
      success: true,
      data: {
        items: [
          {
            id: "co-1",
            slug: "aquabath",
            name: "AQUABATH",
            industry: "Bathware",
            city: "Mumbai",
            country: "India",
            verification_status: "verified",
          },
        ],
        total: 1,
        page: 1,
        page_size: 6,
        total_pages: 1,
      },
      meta: { requestId: "x", timestamp: "now" },
    });

    render(<AISearchBar />);
    const input = screen.getByLabelText("Ask ForgeX AI");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Aquabath" } });

    await waitFor(() => expect(screen.getByText("AQUABATH")).toBeTruthy());
    expect(vi.mocked(searchCompanies)).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Aquabath" })
    );
  });

  it("clicking a live company-name match still navigates to that company's profile, not Consult", async () => {
    vi.mocked(searchCompanies).mockResolvedValue({
      success: true,
      data: {
        items: [
          {
            id: "co-1",
            slug: "aquabath",
            name: "AQUABATH",
            industry: "Bathware",
            city: "Mumbai",
            country: "India",
            verification_status: "verified",
          },
        ],
        total: 1,
        page: 1,
        page_size: 6,
        total_pages: 1,
      },
      meta: { requestId: "x", timestamp: "now" },
    });

    render(<AISearchBar />);
    const input = screen.getByLabelText("Ask ForgeX AI");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Aquabath" } });

    await waitFor(() => expect(screen.getByText("AQUABATH")).toBeTruthy());
    fireEvent.click(screen.getByText("AQUABATH"));
    expect(pushMock).toHaveBeenCalledWith("/company/aquabath");
  });

  it("every rotating placeholder is a sourcing-style query, not a company-comparison request Consult can't answer", async () => {
    const { AISearchBar: Bar } = await import("@/components/home/AISearchBar");
    render(<Bar />);
    const input = screen.getByLabelText("Ask ForgeX AI") as HTMLInputElement;
    expect(input.placeholder.toLowerCase()).not.toContain("compare");
  });
});
