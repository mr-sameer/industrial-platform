/**
 * Requirement Intelligence & Matching API client functions — wires the
 * Consult UI to the real Module 7A-1/7A-2 backend. Mirrors
 * lib/companies.ts's conventions exactly (plain Bearer auth, no BFF —
 * same reasoning as that file's own docstring). Both endpoints require
 * an authenticated caller (see apps/api/app/api/v1/requirements.py's
 * own docstring: anonymous submission was deliberately not built
 * there) — the access token is passed in explicitly by the call site,
 * never read from this module.
 */
import type {
  RequirementCreateRequest,
  RequirementDetail,
  RequirementMatchesResponse,
} from "@platform/shared-types";

import { apiFetch } from "@/lib/api-client";

function authHeaders(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` };
}

export function createRequirement(payload: RequirementCreateRequest, accessToken: string) {
  return apiFetch<RequirementDetail>("/api/v1/requirements", {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

export function getRequirementMatches(requirementId: string, accessToken: string) {
  return apiFetch<RequirementMatchesResponse>(`/api/v1/requirements/${requirementId}/matches`, {
    headers: authHeaders(accessToken),
  });
}
