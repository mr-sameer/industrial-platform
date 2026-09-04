import { describe, expect, it } from "vitest";

import { extractTechnicalCriteria } from "@/lib/requirement";

/**
 * extractTechnicalCriteria is the first MVP technical-criteria layer:
 * deterministic, explicit-vocabulary extraction of a numeric
 * constraint ("motor power at least 3 kW") into a real
 * RequirementSpecificationCriterionInput, against the REAL
 * specifications of an already-resolved category. Same "ask, don't
 * guess" discipline as every other extractor in lib/requirement.ts —
 * a criterion is produced ONLY when spec phrase + operator phrase +
 * number + matching unit are ALL explicitly present; never a default
 * "=", never a unit conversion, never a fuzzy match.
 *
 * Fixture specs mirror the real canonical Industrial Pumps pilot
 * category exactly (Motor Power/kW/number, Flow Rate/m3/hr/number,
 * Head/m/number, Pump Type/text) — fabricated test-only UUIDs, no
 * database access, per this task's own instruction to mock/fix the
 * specification response rather than touch real DB state.
 */
const MOTOR_POWER_ID = "spec-motor-power";
const FLOW_RATE_ID = "spec-flow-rate";
const HEAD_ID = "spec-head";
const PUMP_TYPE_ID = "spec-pump-type";

const INDUSTRIAL_PUMPS_SPECS = [
  { id: MOTOR_POWER_ID, category_id: "cat-pumps", name: "Motor Power", unit: "kW", datatype: "number" as const, enum_options: null, required: false },
  { id: FLOW_RATE_ID, category_id: "cat-pumps", name: "Flow Rate", unit: "m3/hr", datatype: "number" as const, enum_options: null, required: false },
  { id: HEAD_ID, category_id: "cat-pumps", name: "Head", unit: "m", datatype: "number" as const, enum_options: null, required: false },
  { id: PUMP_TYPE_ID, category_id: "cat-pumps", name: "Pump Type", unit: null, datatype: "text" as const, enum_options: null, required: false },
];

describe("extractTechnicalCriteria", () => {
  it("extracts 'at least <N> <unit> <spec>' (operator-first order)", () => {
    const criteria = extractTechnicalCriteria(
      "I need a pump with at least 3 kW motor power",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: MOTOR_POWER_ID, operator: "gte", value: 3 }]);
  });

  it("extracts '<spec> above <N> <unit>' (spec-first order)", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with motor power above 5 kW",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: MOTOR_POWER_ID, operator: "gte", value: 5 }]);
  });

  it("extracts 'head of at least <N> m'", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with head of at least 50 m",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: HEAD_ID, operator: "gte", value: 50 }]);
  });

  it("extracts 'flow rate above <N> m3/hr'", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with flow rate above 20 m3/hr",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: FLOW_RATE_ID, operator: "gte", value: 20 }]);
  });

  it("recognizes the m³/hr (superscript) unit form too, not only the ASCII m3/hr form", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with flow rate above 20 m³/hr",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: FLOW_RATE_ID, operator: "gte", value: 20 }]);
  });

  it("produces no technical criterion for a bare quantity sentence, even though a number and 'kW' both appear", () => {
    const criteria = extractTechnicalCriteria(
      "Need 500 pumps with 3 kW motors",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([]);
  });

  it("produces no criterion when a unit is stated but no operator phrase is present", () => {
    const criteria = extractTechnicalCriteria(
      "Looking for a pump with 2.2 kW motor",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([]);
  });

  it("produces no criterion for an unsupported unit (HP), even with a clear operator", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with at least 3 HP motor power",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([]);
  });

  it("produces no criterion for a raw watts value (no kW->W conversion, no bare-W match)", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with at least 3000 W motor power",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([]);
  });

  it("extracts two independent criteria from one sentence", () => {
    const criteria = extractTechnicalCriteria(
      "I need a pump with at least 3 kW motor power and head above 50 m",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toHaveLength(2);
    expect(criteria).toContainEqual({ specification_id: MOTOR_POWER_ID, operator: "gte", value: 3 });
    expect(criteria).toContainEqual({ specification_id: HEAD_ID, operator: "gte", value: 50 });
  });

  it("produces no criterion for a bare technical value with no comparison word — never defaults to '='", () => {
    const criteria = extractTechnicalCriteria("Need a pump with 3 kW power", INDUSTRIAL_PUMPS_SPECS);
    expect(criteria).toEqual([]);
  });

  it("recognizes 'lte'-mapped operator phrases (at most / maximum / below / less than)", () => {
    for (const phrase of ["at most", "maximum", "below", "less than"]) {
      const criteria = extractTechnicalCriteria(
        `Need a pump with motor power ${phrase} 5 kW`,
        INDUSTRIAL_PUMPS_SPECS
      );
      expect(criteria).toEqual([{ specification_id: MOTOR_POWER_ID, operator: "lte", value: 5 }]);
    }
  });

  it("never produces a criterion for Pump Type (text datatype) even if the word appears near a number/unit", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump type rated at least 3 kW",
      INDUSTRIAL_PUMPS_SPECS
    );
    // Only Motor Power should fire ("at least 3 kW" + no Pump Type
    // alias matches this phrasing at all) — this asserts Pump Type
    // specifically never appears in the output.
    expect(criteria.every((c) => c.specification_id !== PUMP_TYPE_ID)).toBe(true);
  });

  it("recognizes the 'discharge' alias for Flow Rate", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with discharge above 20 m3/hr",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: FLOW_RATE_ID, operator: "gte", value: 20 }]);
  });

  it("returns [] when the category has none of the supported specifications", () => {
    const criteria = extractTechnicalCriteria("I need at least 3 kW motor power", [
      { id: "spec-other", category_id: "cat-other", name: "Bore Diameter", unit: "mm", datatype: "number", enum_options: null, required: false },
    ]);
    expect(criteria).toEqual([]);
  });

  it("returns [] for an empty specification list (unresolved category)", () => {
    expect(extractTechnicalCriteria("I need at least 3 kW motor power", [])).toEqual([]);
  });

  it("skips a specification whose real configured unit isn't a recognized variant, rather than matching it anyway", () => {
    const criteria = extractTechnicalCriteria("Need at least 3 kW motor power", [
      { id: "spec-mp-hp", category_id: "cat-pumps", name: "Motor Power", unit: "HP", datatype: "number", enum_options: null, required: false },
    ]);
    expect(criteria).toEqual([]);
  });

  it("is case-insensitive on both the spec phrase and the operator phrase", () => {
    const criteria = extractTechnicalCriteria(
      "Need a pump with MOTOR POWER ABOVE 5 KW",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([{ specification_id: MOTOR_POWER_ID, operator: "gte", value: 5 }]);
  });
});

/**
 * Pump Type (text, eq) — extends extractTechnicalCriteria to support a
 * buyer's explicit product-type statement ("a centrifugal pump"). The
 * criterion's `value` is the FULL canonical ProductAttribute string
 * ("Vertical Multistage Centrifugal Pump" / "Submersible Motor
 * Pumpset"), never the buyer's own short phrase — the backend's `eq`
 * operator for text specs is exact, case-insensitive WHOLE-STRING
 * equality (app.services.requirement_matching_service
 * ._evaluate_criterion), never substring/fuzzy. A criterion of value
 * "centrifugal" could never equal "Vertical Multistage Centrifugal
 * Pump" and would silently exclude every real candidate — see
 * lib/requirement.ts's own PUMP_TYPE_PHRASE_TO_CANONICAL docstring.
 */
describe("extractTechnicalCriteria — Pump Type equality", () => {
  it("extracts a Pump Type criterion for 'centrifugal', mapped to the real CRI canonical value", () => {
    const criteria = extractTechnicalCriteria("I need a centrifugal pump", INDUSTRIAL_PUMPS_SPECS);
    expect(criteria).toEqual([
      { specification_id: PUMP_TYPE_ID, operator: "eq", value: "Vertical Multistage Centrifugal Pump" },
    ]);
  });

  it("extracts a Pump Type criterion for 'submersible', mapped to the real KSB canonical value", () => {
    const criteria = extractTechnicalCriteria("I need a submersible pump", INDUSTRIAL_PUMPS_SPECS);
    expect(criteria).toEqual([
      { specification_id: PUMP_TYPE_ID, operator: "eq", value: "Submersible Motor Pumpset" },
    ]);
  });

  it("extracts a Pump Type criterion for the exact canonical phrase itself", () => {
    const criteria = extractTechnicalCriteria(
      "I need a vertical multistage centrifugal pump",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toEqual([
      { specification_id: PUMP_TYPE_ID, operator: "eq", value: "Vertical Multistage Centrifugal Pump" },
    ]);
  });

  it("produces no Pump Type criterion when no type phrase is stated", () => {
    const criteria = extractTechnicalCriteria(
      "I need an industrial pump with at least 3 kW motor power",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria.some((c) => c.specification_id === PUMP_TYPE_ID)).toBe(false);
  });

  it("produces both a Pump Type and a Motor Power criterion together ('centrifugal' + kW)", () => {
    const criteria = extractTechnicalCriteria(
      "I need a centrifugal pump with at least 3 kW motor power",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toHaveLength(2);
    expect(criteria).toContainEqual({
      specification_id: PUMP_TYPE_ID, operator: "eq", value: "Vertical Multistage Centrifugal Pump",
    });
    expect(criteria).toContainEqual({ specification_id: MOTOR_POWER_ID, operator: "gte", value: 3 });
  });

  it("produces both a Pump Type and a Motor Power criterion together ('submersible' + kW)", () => {
    const criteria = extractTechnicalCriteria(
      "I need a submersible pump with at least 3 kW motor power",
      INDUSTRIAL_PUMPS_SPECS
    );
    expect(criteria).toHaveLength(2);
    expect(criteria).toContainEqual({
      specification_id: PUMP_TYPE_ID, operator: "eq", value: "Submersible Motor Pumpset",
    });
    expect(criteria).toContainEqual({ specification_id: MOTOR_POWER_ID, operator: "gte", value: 3 });
  });

  it("produces no Pump Type criterion for an unrelated sentence ('for irrigation')", () => {
    const criteria = extractTechnicalCriteria("Need a pump for irrigation", INDUSTRIAL_PUMPS_SPECS);
    expect(criteria).toEqual([]);
  });

  it("never infers Pump Type from the specification list alone — an empty/unresolved category yields nothing", () => {
    expect(extractTechnicalCriteria("I need a centrifugal pump", [])).toEqual([]);
  });

  it("does not fire on a Pump Type-named specification that isn't actually text datatype", () => {
    const criteria = extractTechnicalCriteria("I need a centrifugal pump", [
      { id: "spec-weird", category_id: "cat-pumps", name: "Pump Type", unit: null, datatype: "number", enum_options: null, required: false },
    ]);
    expect(criteria).toEqual([]);
  });

  it("real pilot semantics: a centrifugal-type criterion rejects KSB's real Submersible value and accepts CRI's real Vertical Multistage Centrifugal value under the backend's exact-equality rule", () => {
    // This test asserts the VALUE shape only (extractTechnicalCriteria
    // never touches the matcher) — the actual eq-equality evaluation
    // itself is backend code (app.services.requirement_matching_service),
    // covered separately by the Python test suite and the real
    // canonical-pilot acceptance run. What's asserted here is that the
    // frontend emits the one value ("Vertical Multistage Centrifugal
    // Pump") that will correctly match CRI and correctly fail to match
    // KSB's real, different, real value ("Submersible Motor Pumpset")
    // under plain case-insensitive string equality.
    const criteria = extractTechnicalCriteria("I need a centrifugal pump", INDUSTRIAL_PUMPS_SPECS);
    const value = criteria[0]!.value as string;
    const cri_real_value = "Vertical Multistage Centrifugal Pump";
    const ksb_real_value = "Submersible Motor Pumpset";
    expect(value.toLowerCase()).toBe(cri_real_value.toLowerCase());
    expect(value.toLowerCase()).not.toBe(ksb_real_value.toLowerCase());
  });
});
