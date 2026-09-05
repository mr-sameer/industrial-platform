import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import ConsultPage from "@/app/consult/page";
import { listCategories, listCategorySpecifications } from "@/lib/products";
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
  listCategorySpecifications: vi.fn(),
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
    // sessionStorage persists across tests within a jsdom file (unlike
    // the rendered DOM, which testing-library auto-cleans) — without
    // this, the "prompts login instead of calling the backend" test
    // below writes a pending-search entry (P0 #1's auth_required save,
    // see app/consult/page.tsx) that a later authenticated test would
    // then silently restore, skipping its own greeting phase.
    sessionStorage.clear();
    authState.status = "authenticated";
    authState.accessToken = "token-abc";
    vi.mocked(listCategories).mockResolvedValue({
      success: true,
      data: [{ id: "cat-1", name: "custom parts", slug: "custom-parts", parent_id: null }],
      meta: okMeta,
    });
    // No technical specification recognized by extractTechnicalCriteria
    // in this file's fixtures ("custom parts" isn't the Industrial
    // Pumps pilot) — an empty real specs response is the honest
    // behavior, and keeps every pre-existing assertion of
    // `criteria: []` in this file correct unchanged.
    vi.mocked(listCategorySpecifications).mockResolvedValue({
      success: true,
      data: [],
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
            offering: { role: "manufacturer", verification_status: "unverified", moq: null, lead_time: null, capacity: null },
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

  it("extracts a real technical criterion from buyer text and reaches the backend payload — the first MVP technical-criteria acceptance test", async () => {
    const MOTOR_POWER_ID = "spec-motor-power-real-id";
    vi.mocked(listCategories).mockResolvedValue({
      success: true,
      data: [{ id: "cat-pumps", name: "Industrial Pumps", slug: "industrial-pumps", parent_id: null }],
      meta: okMeta,
    });
    vi.mocked(listCategorySpecifications).mockResolvedValue({
      success: true,
      data: [
        { id: MOTOR_POWER_ID, category_id: "cat-pumps", name: "Motor Power", unit: "kW", datatype: "number", enum_options: null, required: false },
        { id: "spec-flow-rate", category_id: "cat-pumps", name: "Flow Rate", unit: "m3/hr", datatype: "number", enum_options: null, required: false },
        { id: "spec-head", category_id: "cat-pumps", name: "Head", unit: "m", datatype: "number", enum_options: null, required: false },
        { id: "spec-pump-type", category_id: "cat-pumps", name: "Pump Type", unit: null, datatype: "text", enum_options: null, required: false },
      ],
      meta: okMeta,
    });
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
    const input = screen.getByLabelText("Your message");
    fireEvent.change(input, { target: { value: "I need an industrial pump with at least 3 kW motor power" } });
    fireEvent.submit(input.closest("form")!);
    // No role keyword ("manufacturer"/"supplier"/...) in this sentence,
    // so intent is the first clarifying question, same chip set
    // driveToSummary() uses elsewhere in this file.
    fireEvent.click(screen.getByText("Manufacturer"));
    fireEvent.click(screen.getByText("India"));
    fireEvent.click(screen.getByText("None"));
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(createRequirement).toHaveBeenCalled());
    const [payload] = vi.mocked(createRequirement).mock.calls[0]!;
    expect(payload.product_category_id).toBe("cat-pumps");
    expect(payload.criteria).toEqual([{ specification_id: MOTOR_POWER_ID, operator: "gte", value: 3 }]);
  });

  /**
   * Regression acceptance test for the real buyer pilot fix: the exact
   * production-like buyer message that previously reached the backend
   * with only a Pump Type criterion (Flow Rate/Head/Motor Power all
   * silently dropped). Drives the real ConsultForm component — not
   * just extractTechnicalCriteria in isolation — end to end through
   * the same createRequirement payload the live app sends, and asserts
   * the "ForgeX understood" panel surfaces both what resolved and the
   * material/regional-preference gaps that don't.
   */
  it("extracts all four technical criteria from the real buyer pilot requirement and shows what ForgeX understood", async () => {
    const FLOW_RATE_ID = "spec-flow-rate-real";
    const HEAD_ID = "spec-head-real";
    const MOTOR_POWER_ID = "spec-motor-power-real";
    const PUMP_TYPE_ID = "spec-pump-type-real";
    const CATEGORY_ID = "cat-centrifugal-pumps";

    vi.mocked(listCategories).mockResolvedValue({
      success: true,
      data: [{ id: CATEGORY_ID, name: "Centrifugal Pumps", slug: "centrifugal-pumps", parent_id: null }],
      meta: okMeta,
    });
    vi.mocked(listCategorySpecifications).mockResolvedValue({
      success: true,
      data: [
        { id: MOTOR_POWER_ID, category_id: CATEGORY_ID, name: "Motor Power", unit: "kW", datatype: "number", enum_options: null, required: false },
        { id: FLOW_RATE_ID, category_id: CATEGORY_ID, name: "Flow Rate", unit: "m3/hr", datatype: "number", enum_options: null, required: false },
        { id: HEAD_ID, category_id: CATEGORY_ID, name: "Head", unit: "m", datatype: "number", enum_options: null, required: false },
        { id: PUMP_TYPE_ID, category_id: CATEGORY_ID, name: "Pump Type", unit: null, datatype: "text", enum_options: null, required: false },
      ],
      meta: okMeta,
    });
    vi.mocked(createRequirement).mockResolvedValue({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      success: true, data: { id: "req-pilot" } as any, meta: okMeta,
    });
    // Mirrors the real matcher's real behavior confirmed against the
    // live dev database: the sole seeded product has no verified Flow
    // Rate/Head evidence, so it is correctly excluded once these four
    // criteria actually reach the backend — zero matches, not a
    // fabricated one.
    vi.mocked(getRequirementMatches).mockResolvedValue({
      success: true,
      data: {
        requirement_id: "req-pilot",
        status: "computed",
        total_candidates_considered: 1,
        more_candidates_may_exist: false,
        excluded_for_hard_criteria: 1,
        returned_count: 0,
        matches: [],
      },
      meta: okMeta,
    });

    const buyerMessage = `We're sourcing a high-pressure vertical multistage centrifugal pump for a boiler feedwater application at a textile processing unit in Gujarat, India.

Technical requirements:
- Pump type: vertical multistage centrifugal (not submersible, not end-suction)
- Flow rate: minimum 15 m3/hr at duty point
- Total head: at least 150 m
- Motor power: should not exceed 15 kW (site has a limited electrical sanction load)
- Wetted parts in stainless steel (SS316 preferred, SS304 acceptable) — handles slightly acidic condensate return
- Must be rated for continuous duty, 24x7 operation across a 3-shift plant

Commercial requirements:
- Manufacturer or authorized distributor based in India, preferably Gujarat, Maharashtra or Tamil Nadu — freight and after-sales response time matter more to us than shaving the last bit off unit price
- Should be able to demonstrate ISO 9001 certification; CE marking is a plus if the same model is also exported
- Initial order is 4 units, with a realistic follow-on of 20+ units/year if this vendor gets qualified for repeat business
- Need the first units within 6-8 weeks of PO — this is tied to a planned shutdown window
- We'd prefer a company with an actual, verifiable track record supplying this pump type into process industries (textile, chemical, or similar), not just a catalog listing

Please shortlist companies/products that can genuinely meet this, and be clear about what's confirmed with evidence versus what's just claimed.`;

    render(<ConsultPage />);
    const input = screen.getByLabelText("Your message");
    fireEvent.change(input, { target: { value: buyerMessage } });
    fireEvent.submit(input.closest("form")!);
    fireEvent.click(screen.getByText("Search now"));

    await waitFor(() => expect(createRequirement).toHaveBeenCalled());
    const [payload] = vi.mocked(createRequirement).mock.calls[0]!;
    expect(payload.product_category_id).toBe(CATEGORY_ID);
    expect(payload.criteria).toHaveLength(4);
    expect(payload.criteria).toContainEqual({ specification_id: FLOW_RATE_ID, operator: "gte", value: 15 });
    expect(payload.criteria).toContainEqual({ specification_id: HEAD_ID, operator: "gte", value: 150 });
    expect(payload.criteria).toContainEqual({ specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 });
    expect(payload.criteria).toContainEqual({
      specification_id: PUMP_TYPE_ID,
      operator: "eq",
      value: "Vertical Multistage Centrifugal Pump",
    });

    // The honest no-match state renders (the backend correctly excluded
    // the only candidate) — and the "ForgeX understood" panel shows all
    // four resolved criteria plus the material and regional-preference
    // gaps, rather than the requirement silently vanishing.
    await waitFor(() => expect(screen.getByText(/growing daily/)).toBeTruthy());
    expect(screen.getByText("Flow Rate: >= 15 m3/hr")).toBeTruthy();
    expect(screen.getByText("Head: >= 150 m")).toBeTruthy();
    expect(screen.getByText("Motor Power: <= 15 kW")).toBeTruthy();
    expect(screen.getByText("Pump Type: = Vertical Multistage Centrifugal Pump")).toBeTruthy();
    expect(screen.getByText(/Regional preference noted: Gujarat, Maharashtra, Tamil Nadu/)).toBeTruthy();
    expect(screen.getByText(/Material \/ wetted-parts construction requirement is not currently matchable/)).toBeTruthy();
  });
});
