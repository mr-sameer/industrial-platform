import { describe, expect, it } from "vitest";

import {
  detectAmbiguousTechnicalMentions,
  detectUnsupportedTechnicalMentions,
  extractRegionalPreference,
  extractTechnicalCriteria,
  formatTechnicalCriteria,
} from "@/lib/requirement";

/**
 * Regression coverage for the real buyer pilot audit: a genuine buyer
 * wrote "Flow rate: minimum 15 m3/hr", "Total head: at least 150 m",
 * and "Motor power: should not exceed 15 kW" — ordinary RFQ phrasing —
 * and extractTechnicalCriteria's original 5-phrase-per-direction
 * vocabulary and bare `\s*` separator silently dropped all three, with
 * nothing anywhere telling the buyer this had happened. This file
 * covers the widened operator vocabulary, the punctuation-tolerant
 * separator, the four supported phrase orders, and the new
 * ambiguous/unsupported/regional-preference detectors that make a
 * genuinely undetectable requirement visible instead of silent.
 */

const MOTOR_POWER_ID = "spec-motor-power";
const FLOW_RATE_ID = "spec-flow-rate";
const HEAD_ID = "spec-head";
const PUMP_TYPE_ID = "spec-pump-type";

const CENTRIFUGAL_PUMPS_SPECS = [
  { id: MOTOR_POWER_ID, category_id: "cat-pumps", name: "Motor Power", unit: "kW", datatype: "number" as const, enum_options: null, required: false },
  { id: FLOW_RATE_ID, category_id: "cat-pumps", name: "Flow Rate", unit: "m3/hr", datatype: "number" as const, enum_options: null, required: false },
  { id: HEAD_ID, category_id: "cat-pumps", name: "Head", unit: "m", datatype: "number" as const, enum_options: null, required: false },
  { id: PUMP_TYPE_ID, category_id: "cat-pumps", name: "Pump Type", unit: null, datatype: "text" as const, enum_options: null, required: false },
];

describe("extractTechnicalCriteria — widened operator vocabulary (real buyer pilot fix)", () => {
  describe("GTE phrases", () => {
    it("'minimum'", () => {
      expect(extractTechnicalCriteria("Flow rate minimum 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("'minimum of'", () => {
      expect(extractTechnicalCriteria("Flow rate minimum of 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("'at least'", () => {
      expect(extractTechnicalCriteria("Flow rate at least 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("'>='", () => {
      expect(extractTechnicalCriteria("Flow rate >= 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("postfix '<number> <unit> minimum'", () => {
      expect(extractTechnicalCriteria("Flow rate 15 m3/hr minimum", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("'not less than'", () => {
      expect(extractTechnicalCriteria("Flow rate not less than 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("'minimum head of <N> m' (operator-alias-of-number order)", () => {
      expect(extractTechnicalCriteria("minimum head of 150 m", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: HEAD_ID, operator: "gte", value: 150 },
      ]);
    });

    it("'at least 150 m' for Head", () => {
      expect(extractTechnicalCriteria("Head at least 150 m", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: HEAD_ID, operator: "gte", value: 150 },
      ]);
    });

    it("Head '>= 150 m'", () => {
      expect(extractTechnicalCriteria("Head >= 150 m", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: HEAD_ID, operator: "gte", value: 150 },
      ]);
    });

    it("Head 'not less than 150 m'", () => {
      expect(extractTechnicalCriteria("Head not less than 150 m", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: HEAD_ID, operator: "gte", value: 150 },
      ]);
    });
  });

  describe("LTE phrases", () => {
    it("'should not exceed' — the exact real buyer phrase this fix targets", () => {
      expect(extractTechnicalCriteria("Motor power should not exceed 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("'maximum'", () => {
      expect(extractTechnicalCriteria("Motor power maximum 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("'max'", () => {
      expect(extractTechnicalCriteria("Motor power max 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("'up to'", () => {
      expect(extractTechnicalCriteria("Motor power up to 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("'no more than'", () => {
      expect(extractTechnicalCriteria("Motor power no more than 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("'not more than'", () => {
      expect(extractTechnicalCriteria("Motor power not more than 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("'<='", () => {
      expect(extractTechnicalCriteria("Motor power <= 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
      ]);
    });

    it("does not let 'more than' inside 'not more than' fire a false GTE match", () => {
      const criteria = extractTechnicalCriteria("Motor power not more than 15 kW", CENTRIFUGAL_PUMPS_SPECS);
      expect(criteria).toHaveLength(1);
      expect(criteria[0]!.operator).toBe("lte");
    });

    it("does not let 'less than' inside 'not less than' fire a false LTE match", () => {
      const criteria = extractTechnicalCriteria("Flow rate not less than 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS);
      expect(criteria).toHaveLength(1);
      expect(criteria[0]!.operator).toBe("gte");
    });

    it("'max' does not fire inside the unrelated word 'maximum' twice / double count", () => {
      const criteria = extractTechnicalCriteria("Motor power maximum 15 kW", CENTRIFUGAL_PUMPS_SPECS);
      expect(criteria).toHaveLength(1);
    });
  });

  describe("natural punctuation and formatting", () => {
    it("colon formatting — 'Flow rate: minimum 15 m3/hr'", () => {
      expect(extractTechnicalCriteria("Flow rate: minimum 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("dash formatting — 'Flow rate - minimum 15 m3/hr'", () => {
      expect(extractTechnicalCriteria("Flow rate - minimum 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("em-dash formatting — 'Total head — at least 150 m'", () => {
      expect(extractTechnicalCriteria("Total head — at least 150 m", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: HEAD_ID, operator: "gte", value: 150 },
      ]);
    });

    it("multiline bullet format", () => {
      const text = "Technical requirements:\n- Flow rate: minimum 15 m3/hr at duty point\n- Total head: at least 150 m";
      const criteria = extractTechnicalCriteria(text, CENTRIFUGAL_PUMPS_SPECS);
      expect(criteria).toContainEqual({ specification_id: FLOW_RATE_ID, operator: "gte", value: 15 });
      expect(criteria).toContainEqual({ specification_id: HEAD_ID, operator: "gte", value: 150 });
    });

    it("extra whitespace between spec, operator, number and unit", () => {
      expect(extractTechnicalCriteria("Flow rate    minimum    15   m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("ordinary capitalization variations", () => {
      expect(extractTechnicalCriteria("FLOW RATE: MINIMUM 15 M3/HR", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("m3/hr (ASCII) unit form", () => {
      expect(extractTechnicalCriteria("Flow rate at least 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });

    it("m³/hr (superscript) unit form", () => {
      expect(extractTechnicalCriteria("Flow rate at least 15 m³/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
      ]);
    });
  });

  describe("multiple criteria / mixed hard constraints and preferences", () => {
    it("extracts all three numeric criteria plus Pump Type from one multi-line requirement", () => {
      const text = [
        "We're sourcing a high-pressure vertical multistage centrifugal pump.",
        "- Flow rate: minimum 15 m3/hr at duty point",
        "- Total head: at least 150 m",
        "- Motor power: should not exceed 15 kW (site has a limited electrical sanction load)",
      ].join("\n");
      const criteria = extractTechnicalCriteria(text, CENTRIFUGAL_PUMPS_SPECS);
      expect(criteria).toHaveLength(4);
      expect(criteria).toContainEqual({ specification_id: FLOW_RATE_ID, operator: "gte", value: 15 });
      expect(criteria).toContainEqual({ specification_id: HEAD_ID, operator: "gte", value: 150 });
      expect(criteria).toContainEqual({ specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 });
      expect(criteria).toContainEqual({
        specification_id: PUMP_TYPE_ID,
        operator: "eq",
        value: "Vertical Multistage Centrifugal Pump",
      });
    });

    it("mixes a hard technical constraint with a soft preference sentence without cross-contamination", () => {
      const text = "Flow rate: at least 15 m3/hr. Preferably from a supplier in Gujarat or Maharashtra.";
      const criteria = extractTechnicalCriteria(text, CENTRIFUGAL_PUMPS_SPECS);
      expect(criteria).toEqual([{ specification_id: FLOW_RATE_ID, operator: "gte", value: 15 }]);
    });
  });

  describe("still never infers an operator from a bare number (unchanged discipline)", () => {
    it("'Motor power: 15 kW' produces no criterion — never defaults to <= or >=", () => {
      expect(extractTechnicalCriteria("Motor power: 15 kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
    });

    it("bare 'Flow rate 15 m3/hr' with no operator produces no criterion", () => {
      expect(extractTechnicalCriteria("Flow rate 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
    });
  });

  describe("unsupported units and malformed values still never match", () => {
    it("unsupported unit (HP) even with a recognized new operator", () => {
      expect(extractTechnicalCriteria("Motor power should not exceed 15 HP", CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
    });

    it("unsupported unit (L/min) for Flow Rate even with '>='", () => {
      expect(extractTechnicalCriteria("Flow rate >= 15 L/min", CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
    });

    it("malformed/non-numeric value produces no criterion", () => {
      expect(extractTechnicalCriteria("Flow rate at least fifteen m3/hr", CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
    });

    it("a dangling operator with no number at all produces no criterion", () => {
      expect(extractTechnicalCriteria("Motor power should not exceed kW", CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
    });
  });
});

describe("detectAmbiguousTechnicalMentions", () => {
  it("flags Motor Power as ambiguous when stated as a bare number with no operator", () => {
    const mentions = detectAmbiguousTechnicalMentions("Motor power: 15 kW", CENTRIFUGAL_PUMPS_SPECS);
    expect(mentions).toEqual([{ specificationName: "Motor Power" }]);
  });

  it("does not flag a specification that resolved into a real criterion", () => {
    const mentions = detectAmbiguousTechnicalMentions("Flow rate: at least 15 m3/hr", CENTRIFUGAL_PUMPS_SPECS);
    expect(mentions).toEqual([]);
  });

  it("does not flag a specification never mentioned at all", () => {
    const mentions = detectAmbiguousTechnicalMentions("We need a pump.", CENTRIFUGAL_PUMPS_SPECS);
    expect(mentions).toEqual([]);
  });

  it("does not flag a spec whose alias is mentioned with no accompanying value at all", () => {
    // "motor power" is mentioned in prose but no number/unit follows it
    // anywhere — nothing to be ambiguous about, this is just not a
    // stated technical constraint.
    const mentions = detectAmbiguousTechnicalMentions(
      "Motor power efficiency matters a lot to us in general.",
      CENTRIFUGAL_PUMPS_SPECS
    );
    expect(mentions).toEqual([]);
  });
});

describe("detectUnsupportedTechnicalMentions", () => {
  it("flags material/wetted-parts mentions (SS316/SS304/stainless steel) as not currently matchable", () => {
    const mentions = detectUnsupportedTechnicalMentions(
      "Wetted parts in stainless steel (SS316 preferred, SS304 acceptable)"
    );
    expect(mentions).toContain("Material / wetted-parts construction");
  });

  it("flags an explicit 'lead time' mention", () => {
    expect(detectUnsupportedTechnicalMentions("Lead time must be under 4 weeks")).toContain("Supplier lead time");
  });

  it("returns [] when no unsupported concept is mentioned", () => {
    expect(detectUnsupportedTechnicalMentions("Flow rate at least 15 m3/hr")).toEqual([]);
  });
});

describe("extractRegionalPreference", () => {
  it("extracts a multi-state OR preference without collapsing it into one value", () => {
    expect(extractRegionalPreference("preferably Gujarat, Maharashtra or Tamil Nadu")).toEqual([
      "Gujarat",
      "Maharashtra",
      "Tamil Nadu",
    ]);
  });

  it("returns [] when no known state is mentioned", () => {
    expect(extractRegionalPreference("anywhere in India is fine")).toEqual([]);
  });
});

describe("formatTechnicalCriteria", () => {
  it("renders a human-readable line per criterion using the real specification name and unit", () => {
    const lines = formatTechnicalCriteria(
      [
        { specification_id: FLOW_RATE_ID, operator: "gte", value: 15 },
        { specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 },
        { specification_id: PUMP_TYPE_ID, operator: "eq", value: "Vertical Multistage Centrifugal Pump" },
      ],
      CENTRIFUGAL_PUMPS_SPECS
    );
    expect(lines).toEqual([
      "Flow Rate: >= 15 m3/hr",
      "Motor Power: <= 15 kW",
      "Pump Type: = Vertical Multistage Centrifugal Pump",
    ]);
  });
});

/**
 * The exact production-pilot buyer requirement this fix was audited
 * against (real end-to-end run described in the pilot report): a
 * multi-paragraph, real-world sourcing message that previously reached
 * the backend with only a Pump Type criterion — Flow Rate, Head, and
 * Motor Power were silently dropped, and the sole product in the
 * database (which has no verified Flow Rate/Head evidence) surfaced as
 * a false-positive "match" as a direct result. This is the acceptance
 * test for the fix: all four technical criteria must now reach the
 * payload, none silently dropped.
 */
describe("the exact real buyer pilot requirement — regression acceptance test", () => {
  const BUYER_MESSAGE = `We're sourcing a high-pressure vertical multistage centrifugal pump for a boiler feedwater application at a textile processing unit in Gujarat, India.

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

Please shortlist companies/products that can genuinely meet this, and be clear about what's confirmed with evidence versus what's just claimed.
`;

  it("extracts all four technical criteria — none dropped", () => {
    const criteria = extractTechnicalCriteria(BUYER_MESSAGE, CENTRIFUGAL_PUMPS_SPECS);
    expect(criteria).toHaveLength(4);
    expect(criteria).toContainEqual({ specification_id: FLOW_RATE_ID, operator: "gte", value: 15 });
    expect(criteria).toContainEqual({ specification_id: HEAD_ID, operator: "gte", value: 150 });
    expect(criteria).toContainEqual({ specification_id: MOTOR_POWER_ID, operator: "lte", value: 15 });
    expect(criteria).toContainEqual({
      specification_id: PUMP_TYPE_ID,
      operator: "eq",
      value: "Vertical Multistage Centrifugal Pump",
    });
  });

  it("flags no ambiguous mentions — every supported spec the buyer stated actually resolved", () => {
    expect(detectAmbiguousTechnicalMentions(BUYER_MESSAGE, CENTRIFUGAL_PUMPS_SPECS)).toEqual([]);
  });

  it("flags the material/wetted-parts requirement as not currently matchable", () => {
    expect(detectUnsupportedTechnicalMentions(BUYER_MESSAGE)).toContain("Material / wetted-parts construction");
  });

  it("notes the regional preference without collapsing it into a single filter value", () => {
    expect(extractRegionalPreference(BUYER_MESSAGE)).toEqual(["Gujarat", "Maharashtra", "Tamil Nadu"]);
  });
});
