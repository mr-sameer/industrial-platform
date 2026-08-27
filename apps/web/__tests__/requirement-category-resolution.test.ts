import { describe, expect, it } from "vitest";

import { resolveCategoryId } from "@/lib/requirement";

/**
 * resolveCategoryId is the one piece of new client-side logic this
 * integration adds beyond persistence/rendering — it must stay
 * deterministic (whole-word match against the real category list,
 * never a substring/NLP/LLM guess) since the real Module 7A-2 engine
 * requires product_category_id to run at all.
 */
describe("resolveCategoryId", () => {
  const categories = [
    { id: "cat-cnc", name: "CNC Machining", slug: "cnc-machining", parent_id: null },
    { id: "cat-hydraulic", name: "Hydraulic Cylinders", slug: "hydraulic-cylinders", parent_id: null },
    { id: "cat-cylinders", name: "Cylinders", slug: "cylinders", parent_id: null },
  ];

  it("matches a category whose full name appears as whole words in the text", () => {
    expect(resolveCategoryId(categories, "CNC machining in India")).toBe("cat-cnc");
  });

  it("is case-insensitive", () => {
    expect(resolveCategoryId(categories, "need cnc MACHINING parts")).toBe("cat-cnc");
  });

  it("returns null when no category name appears — an honest unknown, not a guess", () => {
    expect(resolveCategoryId(categories, "need sheet metal stamping")).toBeNull();
  });

  it("never does a blind substring match across word boundaries", () => {
    // "machine" is a substring of "machining" but not the same word —
    // must not match "CNC Machining".
    expect(resolveCategoryId(categories, "need a CNC machine operator")).toBeNull();
  });

  it("prefers the longest (most specific) matching category name", () => {
    expect(resolveCategoryId(categories, "need hydraulic cylinders near Delhi")).toBe("cat-hydraulic");
  });

  it("does not crash when a category name is longer than the requirement text", () => {
    expect(resolveCategoryId(categories, "cylinders")).toBe("cat-cylinders");
    expect(resolveCategoryId(categories, "hi")).toBeNull();
  });

  it("returns null for empty or whitespace-only text", () => {
    expect(resolveCategoryId(categories, "")).toBeNull();
    expect(resolveCategoryId(categories, "   ")).toBeNull();
  });
});
