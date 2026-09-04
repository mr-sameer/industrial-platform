import { describe, expect, it } from "vitest";

import { extractFromText, newRequirementObject } from "@/lib/requirement";

/**
 * extractFromText is the deterministic (no NLP/LLM) free-text
 * extractor behind Consult's opening message. These tests cover the
 * gap found by real buyer validation: explicit quantity/timeline/city
 * constraints were being silently lost even when the buyer stated them
 * plainly, while vague phrases must still never be turned into an
 * invented number — "explicit = capture, not stated = Unknown,
 * ambiguous = Unknown," never guessed.
 */
describe("extractFromText — structured field extraction", () => {
  it("extracts an explicit digit quantity adjacent to a unit word", () => {
    const req = extractFromText(newRequirementObject("x"), "I need a Jacuzzi bathtub, 1 unit, delivered in Delhi.", true);
    expect(req.quantity).toEqual({ value: "1", confidence: "explicit" });
  });

  it("extracts an explicit word-form quantity ('one unit') — the real second buyer's exact phrasing", () => {
    const req = extractFromText(newRequirementObject("x"), "I need a manufacturer for room heaters, one unit, preferably in Delhi.", true);
    expect(req.quantity).toEqual({ value: "1", confidence: "explicit" });
  });

  it("does not invent a quantity from an unrelated number in the sentence", () => {
    const req = extractFromText(newRequirementObject("x"), "delivered within 5 days, need it by 2027", true);
    expect(req.quantity.value).toBeNull();
    expect(req.quantity.confidence).toBe("missing");
  });

  it("extracts an explicit numeric timeline ('within 5 days')", () => {
    const req = extractFromText(newRequirementObject("x"), "Jacuzzi bathtub delivered within 5 days please.", true);
    expect(req.timeline).toEqual({ value: "5 days", confidence: "explicit" });
  });

  it("extracts a word-form timeline ('two weeks')", () => {
    const req = extractFromText(newRequirementObject("x"), "need it within two weeks", true);
    expect(req.timeline).toEqual({ value: "2 weeks", confidence: "explicit" });
  });

  it("never invents a numeric timeline from a vague phrase like 'quickly' — must remain Unknown", () => {
    const req = extractFromText(newRequirementObject("x"), "I need a manufacturer for room heaters and I need it quickly.", true);
    expect(req.timeline.value).toBeNull();
    expect(req.timeline.confidence).toBe("missing");
  });

  it("never invents a numeric timeline from other vague urgency words either", () => {
    for (const phrase of ["ASAP", "urgently", "as soon as possible", "immediately"]) {
      const req = extractFromText(newRequirementObject("x"), `need this ${phrase}`, true);
      expect(req.timeline.value).toBeNull();
    }
  });

  it("extracts an explicit city from the real known-cities list", () => {
    const req = extractFromText(newRequirementObject("x"), "preferably in Delhi", true);
    expect(req.city).toEqual({ value: "Delhi", confidence: "explicit" });
  });

  it("leaves city Unknown when none of the known cities are mentioned", () => {
    const req = extractFromText(newRequirementObject("x"), "preferably somewhere nearby", true);
    expect(req.city.value).toBeNull();
    expect(req.city.confidence).toBe("missing");
  });

  it("captures an explicit certification requirement as a real, uninterpreted claim — never as 'verified'", () => {
    const req = extractFromText(newRequirementObject("x"), "need a valid ISO certificate", true);
    expect(req.certifications).toEqual({ value: ["ISO"], confidence: "explicit" });
  });

  it("captures the full real Jacuzzi buyer requirement's constraints together", () => {
    const req = extractFromText(
      newRequirementObject("x"),
      "I need to find a genuine manufacturer for a Jacuzzi bathtub, 1 unit, delivered within 5 days, preferably in Delhi. Need a valid certificate too.",
      true
    );
    expect(req.quantity.value).toBe("1");
    expect(req.timeline.value).toBe("5 days");
    expect(req.city.value).toBe("Delhi");
    expect(req.country.value).toBeNull(); // "Delhi" is a city, not a country — never conflated
  });

  it("captures the full real room-heater buyer requirement's constraints together, leaving timeline honestly Unknown", () => {
    const req = extractFromText(
      newRequirementObject("x"),
      "I need a manufacturer for room heaters, one unit, preferably in Delhi, and I need it quickly.",
      true
    );
    expect(req.quantity.value).toBe("1");
    expect(req.city.value).toBe("Delhi");
    expect(req.timeline.value).toBeNull(); // "quickly" must never become a number
  });

  it("only ever narrows — never overwrites a field the object already has", () => {
    const first = extractFromText(newRequirementObject("x"), "1 unit needed", true);
    const second = extractFromText(first, "actually make it 5 units", false);
    expect(second.quantity.value).toBe("1"); // the first explicit value is never silently replaced
  });

  /**
   * Regression coverage for the real bug the audit found: an opening
   * message stating quantity/budget/timeline via a "<label> <value>"
   * shape ("quantity 500", "budget 20000 USD", "timeline 2 months")
   * instead of the original "<number> <unit word>" shape had all three
   * fall through to Unknown, and the entire unstripped phrase — label
   * words and all — was dumped into productOrCategory instead. Each
   * field below is tested in isolation, then combined, mirroring the
   * real reported sentence exactly.
   */
  describe("label-prefixed field extraction (the reported regression)", () => {
    it("extracts a quantity stated as 'quantity <number>', not just '<number> units'", () => {
      const req = extractFromText(newRequirementObject("x"), "I need a room heater manufacturer, quantity 500", true);
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
    });

    it("extracts a quantity stated as 'qty: <number>'", () => {
      const req = extractFromText(newRequirementObject("x"), "need CNC parts, qty: 250", true);
      expect(req.quantity).toEqual({ value: "250", confidence: "explicit" });
    });

    it("extracts a budget stated as 'budget <number> <currency>'", () => {
      const req = extractFromText(newRequirementObject("x"), "need a manufacturer, budget 20000 USD", true);
      expect(req.budget).toEqual({ value: "20000 USD", confidence: "explicit" });
    });

    it("extracts a budget with a leading currency symbol ('budget: $20,000')", () => {
      const req = extractFromText(newRequirementObject("x"), "need a supplier, budget: $20,000", true);
      expect(req.budget).toEqual({ value: "20,000 $", confidence: "explicit" });
    });

    it("extracts a budget with no currency at all ('budget of 15000')", () => {
      const req = extractFromText(newRequirementObject("x"), "need a supplier, budget of 15000", true);
      expect(req.budget).toEqual({ value: "15000", confidence: "explicit" });
    });

    it("never invents a budget from a bare number with no 'budget' keyword — the same 'ask, don't guess' rule as quantity/timeline", () => {
      const req = extractFromText(newRequirementObject("x"), "need 20000 pieces of packaging", true);
      expect(req.budget.value).toBeNull();
      expect(req.budget.confidence).toBe("missing");
    });

    it("extracts a timeline stated in months, not just days/weeks/hours", () => {
      const req = extractFromText(newRequirementObject("x"), "need a manufacturer, timeline 2 months", true);
      expect(req.timeline).toEqual({ value: "2 months", confidence: "explicit" });
    });

    it("extracts a timeline stated in years", () => {
      const req = extractFromText(newRequirementObject("x"), "need a supplier, delivery within 1 year", true);
      expect(req.timeline).toEqual({ value: "1 year", confidence: "explicit" });
    });

    it("extracts the real reported sentence's quantity, budget, and timeline together, none left Unknown", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need a room heater manufacturer, quantity 500, budget 20000 USD, timeline 2 months",
        true
      );
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
      expect(req.budget).toEqual({ value: "20000 USD", confidence: "explicit" });
      expect(req.timeline).toEqual({ value: "2 months", confidence: "explicit" });
    });

    it("isolates productOrCategory away from the leaked quantity/budget/timeline text — the actual reported defect", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need a room heater manufacturer, quantity 500, budget 20000 USD, timeline 2 months",
        true
      );
      // Not asserting one exact string — the article "a" and inter-word
      // spacing are pre-existing, unrelated cosmetic behavior. What
      // this regression is actually about: the raw field text must be
      // gone, and "room heater" must still be readable in what's left.
      expect(req.productOrCategory.value).toContain("room heater");
      expect(req.productOrCategory.value).not.toMatch(/quantity|budget|timeline|\d/i);
    });

    it("combines city, country, certification, quantity, budget, and timeline in one sentence without cross-contamination", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need a room heater manufacturer, quantity 500, budget 20000 USD, timeline 2 months, in Mumbai, India, ISO certified",
        true
      );
      expect(req.city.value).toBe("Mumbai");
      expect(req.country.value).toBe("India");
      expect(req.certifications.value).toEqual(["ISO"]);
      expect(req.quantity.value).toBe("500");
      expect(req.budget.value).toBe("20000 USD");
      expect(req.timeline.value).toBe("2 months");
      expect(req.productOrCategory.value).toContain("room heater");
      expect(req.productOrCategory.value).not.toMatch(/quantity|budget|timeline|iso|\d/i);
    });

    it("collapses multiple internal commas left by stripping several adjacent fields, not just a leftover double-comma", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need a room heater manufacturer, quantity 500, budget 20000 USD, timeline 2 months",
        true
      );
      expect(req.productOrCategory.value).not.toMatch(/,\s*,/);
      expect(req.productOrCategory.value).not.toMatch(/quantity|budget|timeline/i);
    });

    it("leaves quantity, budget, and timeline all honestly Unknown for a genuinely ambiguous sentence — never guessed", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need a manufacturer for room heaters, need it soon, reasonable price, a few hundred pieces maybe",
        true
      );
      // "soon" is not a number+unit; "reasonable price" has no number at
      // all; "a few hundred" is a vague quantity, not a stated digit —
      // none of these may be turned into an invented value.
      expect(req.timeline.value).toBeNull();
      expect(req.budget.value).toBeNull();
      expect(req.quantity.value).toBeNull();
    });

    it("still resolves the real Jacuzzi buyer sentence correctly with the widened patterns in place (no regression)", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need to find a genuine manufacturer for a Jacuzzi bathtub, 1 unit, delivered within 5 days, preferably in Delhi. Need a valid certificate too.",
        true
      );
      expect(req.quantity.value).toBe("1");
      expect(req.timeline.value).toBe("5 days");
      expect(req.city.value).toBe("Delhi");
      expect(req.budget.value).toBeNull(); // never stated — must stay an honest Unknown
    });
  });

  /**
   * Regression coverage for the ForgeX Product Audit's P0 #2: a
   * quantity stated the way a real buyer actually opens a sourcing
   * message — "I need <number> <product>" / "Need <number> <product>",
   * the exact shape of the homepage's own rotating placeholder ("Need
   * 5,000 hydraulic cylinders") — fell through to Unknown because the
   * only two recognized shapes were "<number> units/pieces/pcs" and
   * "quantity/qty <number>", neither of which matches a number directly
   * followed by the product name itself.
   */
  describe("quantity stated as '<opening phrase> <number> <product>' (ForgeX Product Audit P0 #2)", () => {
    it("extracts the quantity from the audit's exact reported sentence ('I need 2000 stainless steel ball valves...')", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need 2000 stainless steel ball valves for a water treatment plant",
        true
      );
      expect(req.quantity).toEqual({ value: "2000", confidence: "explicit" });
    });

    it("extracts the quantity from the audit's second reported sentence ('I need 500 room heaters...')", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need 500 room heaters for a hotel chain, ISO certified, within 45 days",
        true
      );
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
    });

    it("extracts the quantity from the homepage's own rotating placeholder example ('Need 5,000 hydraulic cylinders')", () => {
      const req = extractFromText(newRequirementObject("x"), "Need 5,000 hydraulic cylinders", true);
      expect(req.quantity).toEqual({ value: "5,000", confidence: "explicit" });
    });

    it("keeps productOrCategory clean of the opening-phrase quantity — no leaked number or leading filler", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need 2000 stainless steel ball valves for a water treatment plant",
        true
      );
      expect(req.productOrCategory.value).not.toMatch(/\d/);
      expect(req.productOrCategory.value).toContain("stainless steel ball valves");
    });

    it("does not fire when the opening phrase isn't immediately followed by a number — no false positive", () => {
      const req = extractFromText(newRequirementObject("x"), "I need a manufacturer for 500 units", true);
      // The number here is captured correctly by the pre-existing
      // "<number> units" rule, not the new opening-phrase rule — this
      // just confirms the new pattern doesn't change this pre-existing,
      // already-correct outcome.
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
    });
  });

  /**
   * Regression coverage for the second, real bug found running the
   * live Consult flow after the P0 #2 fix above: the opening-phrase
   * rule fires on ANY number immediately after "need"/"looking for"/
   * etc., with no check of what follows it — so a measurement ("500 mm
   * pumps"), an electrical rating, or a model year ("2026 model pumps")
   * were all silently misread as a purchase quantity. Also covers a
   * hedge word a real buyer sometimes inserts before the number ("Need
   * about 500 room heaters"), which previously broke the opening
   * pattern's strict adjacency and fell through to Unknown.
   */
  describe("quantity opening-phrase pattern — false positives and hedge words", () => {
    it("extracts 'I need <number> <product>' (bare 'need', not just 'i need')", () => {
      const req = extractFromText(newRequirementObject("x"), "Need 500 pumps", true);
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
    });

    it("extracts a quantity stated via 'we require <number> units'", () => {
      const req = extractFromText(newRequirementObject("x"), "We require 250 units", true);
      expect(req.quantity).toEqual({ value: "250", confidence: "explicit" });
    });

    it("extracts 'looking for <number> <product>'", () => {
      const req = extractFromText(newRequirementObject("x"), "Looking for 100 industrial pumps", true);
      expect(req.quantity).toEqual({ value: "100", confidence: "explicit" });
    });

    it("extracts a quantity through a hedge word ('Need about 500 room heaters')", () => {
      const req = extractFromText(newRequirementObject("x"), "Need about 500 room heaters", true);
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
      expect(req.productOrCategory.value).not.toMatch(/\d/);
      expect(req.productOrCategory.value).toContain("room heater");
    });

    it("does not read a wattage rating glued to the product noun as a quantity ('500W room heaters')", () => {
      const req = extractFromText(newRequirementObject("x"), "Need 500W room heaters", true);
      expect(req.quantity.value).toBeNull();
      expect(req.quantity.confidence).toBe("missing");
    });

    it("does not read a millimeter dimension as a quantity ('500 mm pumps')", () => {
      const req = extractFromText(newRequirementObject("x"), "Need 500 mm pumps", true);
      expect(req.quantity.value).toBeNull();
      expect(req.quantity.confidence).toBe("missing");
    });

    it("does not read a model year as a quantity ('2026 model pumps')", () => {
      const req = extractFromText(newRequirementObject("x"), "Need 2026 model pumps", true);
      expect(req.quantity.value).toBeNull();
      expect(req.quantity.confidence).toBe("missing");
    });

    it("still resolves the exact live-verified full sentence correctly (quantity, no regression on other fields)", () => {
      const req = extractFromText(
        newRequirementObject("x"),
        "I need 500 room heaters for a hotel chain, ISO certified, within 45 days",
        true
      );
      expect(req.quantity).toEqual({ value: "500", confidence: "explicit" });
      expect(req.certifications.value).toEqual(["ISO"]);
      expect(req.timeline).toEqual({ value: "45 days", confidence: "explicit" });
      expect(req.productOrCategory.value).not.toMatch(/\d/);
    });
  });
});
