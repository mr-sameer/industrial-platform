import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import ConsultPage from "@/app/consult/page";
import { listCategories } from "@/lib/products";
import { createRequirement } from "@/lib/requirements-api";

/**
 * P0 #1 (Buyer UX Audit): a logged-out buyer completing the clarify ->
 * summary flow and hitting "Search now" used to lose the entire
 * conversation on the /login round trip, forcing a retype. These cover
 * the sessionStorage handoff added in app/consult/page.tsx: the
 * requirement/messages are saved right when auth_required fires, and
 * restored (as a fresh ConsultForm mount, exactly like the real
 * post-login navigation back to /consult) once auth resolves to
 * "authenticated" again.
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
const PENDING_KEY = "forgex:consult:pending-search";

function driveToSummary() {
  const input = screen.getByLabelText("Your message");
  fireEvent.change(input, { target: { value: "I need custom parts" } });
  fireEvent.submit(input.closest("form")!);
  fireEvent.click(screen.getByText("Manufacturer"));
  fireEvent.click(screen.getByText("India"));
  fireEvent.click(screen.getByText("None"));
}

describe("Consult pending-search restore across the login detour (P0 #1)", () => {
  beforeAll(() => {
    // jsdom doesn't implement scrollIntoView — pre-existing gap, see the
    // other consult test files for the same setup.
    window.HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  beforeEach(() => {
    sessionStorage.clear();
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
    sessionStorage.clear();
  });

  it("saves the built requirement instead of discarding it when Search now hits the auth boundary", async () => {
    authState.status = "unauthenticated";
    authState.accessToken = null;

    render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));

    // handleSearch now awaits auth.resolveAuth() (the P0 auth-race fix)
    // before deciding whether to show this branch, so its side effects —
    // this message and the sessionStorage write below — land a tick
    // after the click, not synchronously within it.
    await waitFor(() => expect(screen.getByText(/Log in to search/)).toBeTruthy());
    const raw = sessionStorage.getItem(PENDING_KEY);
    expect(raw).toBeTruthy();
    const saved = JSON.parse(raw!);
    expect(saved.requirement.rawQuery).toBe("I need custom parts");
    expect(saved.requirement.country.value).toBe("India");
    expect(createRequirement).not.toHaveBeenCalled();
  });

  it("restores the conversation with no retyping on the next mount once authenticated — the real post-/login shape", async () => {
    authState.status = "unauthenticated";
    authState.accessToken = null;
    const { unmount } = render(<ConsultPage />);
    driveToSummary();
    fireEvent.click(screen.getByText("Search now"));
    // Same async-handleSearch reasoning as the test above.
    await waitFor(() => expect(sessionStorage.getItem(PENDING_KEY)).toBeTruthy());
    unmount();

    // AuthProvider wraps the whole app (see app/layout.tsx), so a real
    // post-login client-side navigation back to /consult remounts only
    // ConsultForm with auth.status already "authenticated" — this mirrors
    // that exactly, rather than flipping status on the same instance.
    authState.status = "authenticated";
    authState.accessToken = "token-abc";
    render(<ConsultPage />);

    await waitFor(() => expect(screen.getByText("Search now")).toBeTruthy());
    expect(screen.getByText("I need custom parts")).toBeTruthy();
    // Consumed on restore, not left around to leak into a later visit.
    expect(sessionStorage.getItem(PENDING_KEY)).toBeNull();
  });

  it("leaves an ordinary authenticated visit with nothing pending untouched", () => {
    render(<ConsultPage />);
    expect(
      screen.getByText("Tell me what your business needs — I'll help you find the right company.")
    ).toBeTruthy();
    expect(screen.queryByText("Search now")).toBeNull();
  });
});
