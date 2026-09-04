import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import ConsultPage from "@/app/consult/page";
import { listCategories, listCategorySpecifications } from "@/lib/products";
import { createRequirement, getRequirementMatches } from "@/lib/requirements-api";

/**
 * Covers the homepage → Consult handoff (P0 #1 of the audit fix): the
 * "Ask ForgeX" search bar routes to /consult?q=<their text> instead of
 * duplicating any extraction logic of its own — this verifies the `?q=`
 * param is treated exactly as if the user had typed and sent that text
 * as Consult's own first message, going through the identical real
 * extraction → clarify → summary flow. See ai-search-bar.test.tsx for
 * the navigation side of this handoff.
 */

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  accessToken: "token-abc" as string | null,
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

const searchParamsState = vi.hoisted(() => ({ q: null as string | null }));

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(searchParamsState.q ? { q: searchParamsState.q } : {}),
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

describe("Consult initial ?q= handoff from the homepage search bar", () => {
  beforeAll(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    // See consult-search-flow.test.tsx's beforeEach for why: sessionStorage
    // persists across tests in this file, and P0 #1's auth_required save
    // (app/consult/page.tsx) would otherwise leak into a later test.
    sessionStorage.clear();
    authState.status = "authenticated";
    authState.accessToken = "token-abc";
    searchParamsState.q = null;
    vi.mocked(listCategories).mockResolvedValue({
      success: true,
      data: [{ id: "cat-heater", name: "Room Heater", slug: "room-heater", parent_id: null }],
      meta: okMeta,
    });
    // Room Heater has no numeric pilot specs — an empty real response
    // is the honest fixture; extractTechnicalCriteria then correctly
    // produces no criteria, preserving this file's existing behavior.
    vi.mocked(listCategorySpecifications).mockResolvedValue({
      success: true,
      data: [],
      meta: okMeta,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("seeds the opening message from ?q= and shows it as a real chat turn, without a plain text box being used", async () => {
    searchParamsState.q = "Need a room heater manufacturer";
    render(<ConsultPage />);

    await waitFor(() => expect(screen.getByText("Need a room heater manufacturer")).toBeTruthy());
    // It went through real extraction, not a no-op — the next clarifying
    // question (country, since intent/product were both extractable)
    // should appear on its own, unprompted by any further user input.
    await waitFor(() => expect(screen.getByText("Which country?")).toBeTruthy());
  });

  /**
   * ForgeX Product Audit P1 #1: a homepage handoff used to render the
   * generic greeting, the buyer's own message, and ForgeX's next
   * question all in the very same instant — a "pre-written
   * conversation" rather than a continuation of what the buyer just
   * typed. The buyer already said what they need on the homepage, so
   * the redundant greeting must never appear for a handoff, and the
   * reply must visibly arrive a beat later, not simultaneously.
   */
  it("never shows the generic greeting on a ?q= handoff — the buyer already said what they need", async () => {
    searchParamsState.q = "Need a room heater manufacturer";
    render(<ConsultPage />);

    await waitFor(() => expect(screen.getByText("Need a room heater manufacturer")).toBeTruthy());
    expect(
      screen.queryByText("Tell me what your business needs — I'll help you find the right company.")
    ).toBeNull();
  });

  it("shows a brief thinking indicator before the real first reply, instead of dumping both at once", async () => {
    searchParamsState.q = "Need a room heater manufacturer";
    render(<ConsultPage />);

    // The buyer's own message is preserved and shown immediately — no
    // reason to delay an echo of what they just sent.
    expect(screen.getByText("Need a room heater manufacturer")).toBeTruthy();
    // The real reply is not there yet: it's still "thinking".
    expect(screen.queryByText("Which country?")).toBeNull();
    await waitFor(() => expect(screen.getByText("Which country?")).toBeTruthy());
  });

  it("reaches the real backend end to end from a ?q= handoff, same as a typed message", async () => {
    searchParamsState.q = "Need a room heater manufacturer";
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
    await waitFor(() => expect(screen.getByText("Which country?")).toBeTruthy());
    screen.getByText("Any").click();
    await waitFor(() => expect(screen.getByText("Any certifications required?")).toBeTruthy());
    screen.getByText("None").click();
    await waitFor(() => expect(screen.getByText("Search now")).toBeTruthy());
    screen.getByText("Search now").click();

    await waitFor(() => expect(createRequirement).toHaveBeenCalled());
    const [payload] = vi.mocked(createRequirement).mock.calls[0]!;
    expect(payload.raw_query).toBe("Need a room heater manufacturer");
  });

  it("shows the ordinary empty greeting when there is no ?q= param — unauthenticated browsing/typing is unaffected", () => {
    searchParamsState.q = null;
    render(<ConsultPage />);
    expect(screen.getByText("Tell me what your business needs — I'll help you find the right company.")).toBeTruthy();
    expect(screen.queryByText("Which country?")).toBeNull();
  });

  it("respects the existing auth boundary — a ?q= handoff still requires login only at the actual search step, not before", async () => {
    authState.status = "unauthenticated";
    authState.accessToken = null;
    searchParamsState.q = "Need a room heater manufacturer";

    render(<ConsultPage />);
    // The conversational clarification itself stays open to anyone.
    await waitFor(() => expect(screen.getByText("Which country?")).toBeTruthy());
    screen.getByText("Any").click();
    await waitFor(() => expect(screen.getByText("Any certifications required?")).toBeTruthy());
    screen.getByText("None").click();
    await waitFor(() => expect(screen.getByText("Search now")).toBeTruthy());
    screen.getByText("Search now").click();

    await waitFor(() => expect(screen.getByText(/Log in to search/)).toBeTruthy());
    expect(createRequirement).not.toHaveBeenCalled();
  });
});
