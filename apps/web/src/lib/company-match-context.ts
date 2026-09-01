import type { RequirementMatchCandidate } from "@platform/shared-types";

/**
 * P0 #3 (Buyer UX Audit): the public /company/[slug] page has no
 * requirement/offering context of its own — MOQ, lead time, capacity,
 * certifications and evidence are all per-offering facts scoped to a
 * specific Consult match (see RequirementMatchCandidate's own docstring
 * in packages/shared-types/src/requirement.ts), not something the
 * company-slug endpoint could return in general. Rather than adding a
 * new backend data source, this carries the subset of the match the
 * buyer already saw on the Consult card through the "View company"
 * navigation itself, as a query param — the company page then renders
 * it as a "from your search" section instead of coming up empty.
 *
 * Because this travels through a URL, `parseMatchContext` treats it as
 * untrusted input: shape is checked field-by-field (never a bare JSON.parse
 * cast) and `sourceUrl` is only kept when it's a real http(s) URL, so a
 * hand-crafted query string can't smuggle a javascript: link into the
 * evidence list this renders.
 */

export interface CarriedEvidenceItem {
  fieldName: string;
  valueObserved: string;
  status: string;
  sourceUrl: string | null;
}

export interface CarriedMatchContext {
  productName: string;
  role: string;
  moq: string | null;
  leadTime: string | null;
  capacity: string | null;
  certificationsRequested: string[];
  certificationsEvidenceFound: string[];
  evidence: CarriedEvidenceItem[];
}

const MAX_EVIDENCE_ITEMS = 20;
const MAX_CERTIFICATIONS = 20;

export function encodeMatchContext(match: RequirementMatchCandidate): string {
  const context: CarriedMatchContext = {
    productName: match.product.name,
    role: match.offering.role,
    moq: match.offering.moq,
    leadTime: match.offering.lead_time,
    capacity: match.offering.capacity,
    certificationsRequested: match.signals.certifications.requested,
    certificationsEvidenceFound: match.signals.certifications.evidence_found,
    evidence: match.evidence.map((item) => ({
      fieldName: item.field_name,
      valueObserved: item.value_observed,
      status: item.status,
      sourceUrl: item.source_url,
    })),
  };
  return JSON.stringify(context);
}

function isSafeHttpUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function asStringArray(value: unknown, max: number): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((v): v is string => typeof v === "string").slice(0, max);
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

export function parseMatchContext(raw: string | string[] | undefined): CarriedMatchContext | null {
  if (typeof raw !== "string" || raw.length === 0) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null) return null;
  const obj = parsed as Record<string, unknown>;
  if (typeof obj.productName !== "string" || typeof obj.role !== "string") return null;

  const evidenceRaw = Array.isArray(obj.evidence) ? obj.evidence.slice(0, MAX_EVIDENCE_ITEMS) : [];
  const evidence: CarriedEvidenceItem[] = evidenceRaw
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .filter((item) => typeof item.fieldName === "string" && typeof item.valueObserved === "string")
    .map((item) => ({
      fieldName: item.fieldName as string,
      valueObserved: item.valueObserved as string,
      status: typeof item.status === "string" ? item.status : "observed",
      sourceUrl: isSafeHttpUrl(item.sourceUrl) ? item.sourceUrl : null,
    }));

  return {
    productName: obj.productName,
    role: obj.role,
    moq: asNullableString(obj.moq),
    leadTime: asNullableString(obj.leadTime),
    capacity: asNullableString(obj.capacity),
    certificationsRequested: asStringArray(obj.certificationsRequested, MAX_CERTIFICATIONS),
    certificationsEvidenceFound: asStringArray(obj.certificationsEvidenceFound, MAX_CERTIFICATIONS),
    evidence,
  };
}
