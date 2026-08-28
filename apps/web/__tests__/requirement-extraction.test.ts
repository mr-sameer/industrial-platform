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
});
