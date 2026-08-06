
import { isApiSuccess } from "@platform/shared-types";
import type { ApiResponse } from "@platform/shared-types";
import { describe, expect, it } from "vitest";

describe("isApiSuccess", () => {
  it("narrows a success response", () => {
    const res: ApiResponse<{ ok: boolean }> = {
      success: true,
      data: { ok: true },
      meta: { requestId: "abc", timestamp: new Date().toISOString() },
    };
    expect(isApiSuccess(res)).toBe(true);
  });

  it("narrows an error response", () => {
    const res: ApiResponse<{ ok: boolean }> = {
      success: false,
      error: { code: "TEST_ERROR", message: "boom" },
      meta: { requestId: "abc", timestamp: new Date().toISOString() },
    };
    expect(isApiSuccess(res)).toBe(false);
  });
});
