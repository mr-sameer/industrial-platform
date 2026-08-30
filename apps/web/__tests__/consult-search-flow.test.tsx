import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import ConsultPage from "@/app/consult/page";
import { listCategories } from "@/lib/products";
import { createRequirement, getRequirementMatches } from "@/lib/requirements-api";

/**
 * End-to-end (component-level) coverage of the Consult -> Module
 * 7A-1/7A-2 wiring: a free-text requirement should reach the real
 * backend contract exactly (POST /requirements, then GET
 * /requirements/{id}/matches), never fall back to the old client-only
 * keyword search, and every backend-reported state (computed with
 * results, computed with zero results, category_required, a hard
 * error, and "not logged in") must render its own honest message —
 * never a fabricated positive result.
 */

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  accessToken: "token-abc" as string | null,
  // Real AuthContext.resolveAuth() waits for the bootstrap race, then
  // returns whatever the (by then settled) status/accessToken actually
  // are — this mock has no bootstrap to wait for, so it just reflects
  // this object's current values at call time, same as the real thing
  // does once resolved.
  async resolveAuth() {
    return {
      status: (this.status === "authenticated" ? "authenticated" : "unauthenticated") as
        | "authenticated"
        | "unauthenticated",
      accessToken: this.accessToken,
    };
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

// No test in this file exercises the `?q=` homepage-handoff param (see
// ai-search-bar.test.tsx and consult-initial-query.test.tsx for that) —
// an empty URLSearchParams here just satisfies ConsultForm's
// useSearchParams() call so these existing typed-message-flow tests
// keep working unchanged.
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/products", () => ({
  listCategories: vi.fn(),
}));

vi.mock("@/lib/requirements-api", () => ({
  createRequirement: vi.fn(),
  getRequirementMatches: vi.fn(),
}));

const okMeta = { requestId: "x", timestamp: "now" };

function driveToSummary() {
  const input = screen.getByLabelText("Your message");
  fireEvent.change(input, { target: { value: "I need custom parts" } });
  fireEvent.submit(input.closest("form")!);
  fireEvent.click(screen.getByText("Manufacturer"));
  fireEvent.click(screen.getByText("India"));
  fireEvent.click(screen.getByText("None"));
}

describe("Consult search flow (Module 7A-1/7A-2 integration)", () => {
  beforeAll(() => {
    // jsdom doesn't implement scrollIntoView — a pre-existing gap in the
    // test environment, not something this integration introduced;
    // ConsultPage's own scrollToBottom() calls it on every message.
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    authState.status = "authenticated";
    authState.accessToken = "token-abc";
    vi.mocked(listCategories).mockResolvedValue({
      success: true,
      data: [{ id: "cat-1", name: "custom parts", slug: "custom-parts", parent_id: null }],
      meta: okMeta,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("persists the requirement via the real backend, with criteria reaching it as a real (empty) list", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-1" } as any, meta: okMeta,
    });
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: true,
      data: {
        requirement_id: "req-1",
        status: "computed",
        total_candidates_considered: 0,
        more_candidates_may_exist: false,
        excluded_for_hard_criteria: 0,
        returned_count: 0,
        matches: [],
      },
      meta: okMeta,
    });

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(createRequirement).toHaveBeenCalled());
    const [payload, token] = vi.mocked(createRequirement).mock.calls[0];
    expect(token).toBe("token-abc");
    expect(payload.raw_query).toBe("I need custom parts");
    expect(payload.country).toBe("India");
    expect(payload.certifications).toEqual([]);
    expect(payload.criteria).toEqual([]);
    expect(payload.product_category_id).toBe("cat-1");

    await waitFor(() => expect(getRequirementMatches).toHaveBeenCalledWith("req-1", "token-abc"));
  });

  it("renders real ranked match results with score and company/product info", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-1" } as any, meta: okMeta,
    });
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: true,
      data: {
        requirement_id: "req-1",
        status: "computed",
        total_candidates_considered: 1,
        more_candidates_may_exist: false,
        excluded_for_hard_criteria: 0,
        returned_count: 1,
        matches: [
          {
            offering_id: "off-1",
            rank: 1,
            score: 90,
            company: {
              id: "co-1",
              name: "ABC Engineering",
              slug: "abc",
              verification_level: "business_verified",
            },
            product: { id: "prod-1", name: "Custom Parts", slug: "custom-parts" },
            signals: {
              category: { matched: true },
              criteria: [],
              location: { requested: {}, candidate: {}, points_earned: 0, points_possible: 0 },
              certifications: {
                requested: [],
                evidence_found: [],
                points_earned: 0,
                points_possible: 0,
                confidence: "low",
                note: null,
              },
              trust_tier: { level: "business_verified", points_earned: 25, points_possible: 50 },
            },
            score_breakdown: [{ signal: "trust_tier", weight: 50, points_earned: 25 }],
            offering: { role: "manufacturer", moq: null, lead_time: null, capacity: null },
            evidence: [],
          },
        ],
      },
      meta: okMeta,
    });

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(screen.getByText("ABC Engineering")).toBeTruthy());
    expect(screen.getByText("1 companies match your requirement.")).toBeTruthy();
    expect(screen.getByText("90% match")).toBeTruthy();
  });

  it("shows the honest no-match state when zero candidates survive the hard filter", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-1" } as any, meta: okMeta,
    });
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: true,
      data: {
        requirement_id: "req-1",
        status: "computed",
        total_candidates_considered: 5,
        more_candidates_may_exist: false,
        excluded_for_hard_criteria: 5,
        returned_count: 0,
        matches: [],
      },
      meta: okMeta,
    });

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(screen.getByText(/growing daily/)).toBeTruthy());
  });

  it("shows the honest category_required state instead of guessing a category", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-1" } as any, meta: okMeta,
    });
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: true,
      data: {
        requirement_id: "req-1",
        status: "category_required",
        total_candidates_considered: 0,
        more_candidates_may_exist: false,
        excluded_for_hard_criteria: 0,
        returned_count: 0,
        matches: [],
      },
      meta: okMeta,
    });

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(screen.getByText(/don't recognize/)).toBeTruthy());
  });

  it("shows a backend error state without crashing when Requirement creation fails", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      success: false,
      error: { code: "INTERNAL", message: "boom" },
      meta: okMeta,
    });

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(screen.getByText(/went wrong/)).toBeTruthy());
    expect(getRequirementMatches).not.toHaveBeenCalled();
  });

  it("shows a backend error state without crashing when matches retrieval fails", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-1" } as any, meta: okMeta,
    });
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: false,
      error: { code: "INTERNAL", message: "boom" },
      meta: okMeta,
    });

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(screen.getByText(/went wrong/)).toBeTruthy());
  });

  it("prompts login instead of calling the backend when the user isn't authenticated", async () => {
    authState.status = "unauthenticated";
    authState.accessToken = null;

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(screen.getByText(/Log in to search/)).toBeTruthy());
    expect(createRequirement).not.toHaveBeenCalled();
    expect(getRequirementMatches).not.toHaveBeenCalled();
  });

  it("never issues the old client-only search — createRequirement is always the entry point", async () => {
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-1" } as any, meta: okMeta,
    });
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: true,
      data: {
        requirement_id: "req-1",
        status: "computed",
        total_candidates_considered: 0,
        more_candidates_may_exist: false,
        excluded_for_hard_criteria: 0,
        returned_count: 0,
        matches: [],
      },
      meta: okMeta,
    });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(createRequirement).toHaveBeenCalled());
    // listCategories, createRequirement, getRequirementMatches are all
    // mocked modules here, so no real fetch should ever fire from the
    // search step itself.
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
