/**
 * Requirement Intelligence & Matching types — Module 7A-1/7A-2. Mirrors
 * apps/api/app/schemas/requirement.py field-for-field.
 */

export type RequirementStatus = "draft" | "submitted" | "archived";
export type CriterionOperator = "eq" | "gte" | "lte" | "range" | "in";
export type CriterionValue = number | string | Array<number | string>;

export interface RequirementSpecificationCriterionInput {
  specification_id: string;
  operator: CriterionOperator;
  value: CriterionValue;
}

export interface RequirementSpecificationCriterionPublic {
  id: string;
  specification_id: string;
  specification_name: string;
  operator: CriterionOperator;
  value: CriterionValue;
}

export interface RequirementCreateRequest {
  raw_query: string;
  product_category_id?: string | null;
  industry?: string | null;
  country?: string | null;
  state?: string | null;
  city?: string | null;
  certifications?: string[] | null;
  quantity?: string | null;
  budget?: string | null;
  timeline?: string | null;
  extraction_confidence?: number | null;
  criteria?: RequirementSpecificationCriterionInput[];
}

export interface RequirementDetail {
  id: string;
  created_by: string;
  raw_query: string;
  product_category_id: string | null;
  industry: string | null;
  country: string | null;
  state: string | null;
  city: string | null;
  certifications: string[] | null;
  quantity: string | null;
  budget: string | null;
  timeline: string | null;
  status: RequirementStatus;
  extraction_confidence: number | null;
  criteria: RequirementSpecificationCriterionPublic[];
  created_at: string;
  updated_at: string;
}

// ---- Matches (Module 7A-2) ----

export interface RequirementMatchCategorySignal {
  matched: boolean;
}

export interface RequirementMatchCriterionSignal {
  specification_id: string;
  specification_name: string;
  operator: CriterionOperator;
  requirement_value: CriterionValue;
  candidate_value: string | null;
  status: string;
}

export interface RequirementMatchLocationSignal {
  requested: Record<string, string | null>;
  candidate: Record<string, string | null>;
  points_earned: number;
  points_possible: number;
}

export interface RequirementMatchCertificationSignal {
  requested: string[];
  evidence_found: string[];
  points_earned: number;
  points_possible: number;
  confidence: string;
  note: string | null;
}

export interface RequirementMatchTrustSignal {
  level: string;
  points_earned: number;
  points_possible: number;
}

export interface RequirementMatchSignals {
  category: RequirementMatchCategorySignal;
  criteria: RequirementMatchCriterionSignal[];
  location: RequirementMatchLocationSignal;
  certifications: RequirementMatchCertificationSignal;
  trust_tier: RequirementMatchTrustSignal;
}

export interface RequirementMatchScoreBreakdownEntry {
  signal: string;
  weight: number;
  points_earned: number;
}

export interface RequirementMatchCompanySummary {
  id: string;
  name: string;
  slug: string;
  verification_level: string;
}

export interface RequirementMatchProductSummary {
  id: string;
  name: string;
  slug: string;
}

export interface RequirementMatchCandidate {
  offering_id: string;
  rank: number;
  score: number;
  company: RequirementMatchCompanySummary;
  product: RequirementMatchProductSummary;
  signals: RequirementMatchSignals;
  score_breakdown: RequirementMatchScoreBreakdownEntry[];
}

export interface RequirementMatchesResponse {
  requirement_id: string;
  status: "computed" | "category_required";
  total_candidates_considered: number;
  more_candidates_may_exist: boolean;
  excluded_for_hard_criteria: number;
  returned_count: number;
  matches: RequirementMatchCandidate[];
}
