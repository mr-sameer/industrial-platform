import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import ConsultPage from "@/app/consult/page";
import { listCategories } from "@/lib/products";

/**
 * ForgeX Product Audit P1 #1: Consult's own message composer became a
 * growing multi-line textarea (shared behavior with the homepage bar,
 * see lib/composer.ts) instead of a single-line input — these cover
 * the actual interaction contract: Enter sends, Shift+Enter inserts a
 * real newline instead of sending early, and a long multi-line
 * requirement survives into the conversation exactly as typed.
 */

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  accessToken: "token-abc" as string | null,
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

describe("Consult composer (ForgeX Product Audit P1 #1)", () => {
  beforeAll(() => {
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
  });

  it("sends on a plain Enter", async () => {
    render(<ConsultPage />);
    const input = screen.getByLabelText("Your message");
    fireEvent.change(input, { target: { value: "I need custom parts" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => expect(screen.getByText("I need custom parts")).toBeTruthy());
  });

  it("does not send on Shift+Enter — that's a newline, not a submit", () => {
    render(<ConsultPage />);
    const input = screen.getByLabelText("Your message") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "I need custom parts" } });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: true });

    // Still sitting in the composer, never turned into a sent chat turn —
    // the greeting placeholder (phase "greeting") would have changed to
    // "Type your answer…" (phase "thinking") the moment a real send happened.
    expect(input.placeholder).toBe("e.g. Need CNC machining in India");
    expect(input.value).toBe("I need custom parts");
  });

  it("preserves a long multi-line requirement exactly as typed once sent", async () => {
    render(<ConsultPage />);
    const input = screen.getByLabelText("Your message");
    const longRequirement =
      "We are a hotel chain based in Mumbai.\nWe need 500 room heaters, ISO certified,\ndelivered within 45 days.";
    fireEvent.change(input, { target: { value: longRequirement } });
    fireEvent.submit(input.closest("form")!);

    // Testing Library's default text matcher collapses whitespace
    // (including real newlines) before comparing — disabling that here
    // is the point of the assertion: the literal line breaks the buyer
    // typed must survive into the sent message, not just its words.
    await waitFor(() =>
      expect(screen.getByText(longRequirement, { normalizer: (text) => text })).toBeTruthy()
    );
  });

  it("clears the composer after sending", async () => {
    render(<ConsultPage />);
    const input = screen.getByLabelText("Your message") as HTMLTextAreaElement;
    fireEvent.change(input, { target: { value: "I need custom parts" } });
    fireEvent.submit(input.closest("form")!);

    await waitFor(() => expect(screen.getByText("I need custom parts")).toBeTruthy());
    expect(input.value).toBe("");
  });
});
