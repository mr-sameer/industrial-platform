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

  describe("singular/plural normalization (deterministic, not fuzzy)", () => {
    const realCategories = [
      { id: "cat-room-heater", name: "Room Heater", slug: "room-heater", parent_id: null },
      { id: "cat-bridal-lehenga", name: "Bridal Lehenga", slug: "bridal-lehenga", parent_id: null },
    ];

    it("matches a plural buyer phrasing against a singular category name — the real buyer-validation failure", () => {
      expect(
        resolveCategoryId(realCategories, "I need a manufacturer for room heaters, one unit, preferably in Delhi.")
      ).toBe("cat-room-heater");
    });

    it("matches the second example pair given: bridal lehenga / lehengas", () => {
      expect(resolveCategoryId(realCategories, "looking for bridal lehengas suppliers")).toBe("cat-bridal-lehenga");
    });

    it("still matches the exact singular form (no regression)", () => {
      expect(resolveCategoryId(realCategories, "need a room heater manufacturer")).toBe("cat-room-heater");
    });

    it("leaves double-s and -us endings alone rather than over-stripping ('glass' must never become 'glas')", () => {
      const guardCategories = [
        { id: "cat-glass", name: "Glass Bottles", slug: "glass-bottles", parent_id: null },
        { id: "cat-bus", name: "Bus Parts", slug: "bus-parts", parent_id: null },
      ];
      expect(resolveCategoryId(guardCategories, "need glass bottles")).toBe("cat-glass");
      expect(resolveCategoryId(guardCategories, "need bus parts")).toBe("cat-bus");
      // A genuinely different word must still not match — confirms the
      // guard didn't accidentally widen matching into a fuzzy one.
      expect(resolveCategoryId(guardCategories, "need brass bottles")).toBeNull();
    });

    it("remains an honest unknown for a genuinely ambiguous/unrelated word — never a fuzzy best-effort guess", () => {
      expect(resolveCategoryId(realCategories, "need heating elements for an oven")).toBeNull();
    });
  });
});
