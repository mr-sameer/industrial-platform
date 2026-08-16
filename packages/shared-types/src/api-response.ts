/**
 * Canonical API envelope. Every FastAPI endpoint and every Next.js route
 * handler that talks to the API returns data matching one of these shapes.
 * See docs/standards/api-response-standard.md for the full spec.
 */

export interface ApiMeta {
  requestId: string;
  timestamp: string; // ISO-8601
}

export interface ApiSuccess<T> {
  success: true;
  data: T;
  meta: ApiMeta;
}

export interface ApiErrorDetail {
  code: string; // machine-readable, SCREAMING_SNAKE_CASE, e.g. "VALIDATION_ERROR"
  message: string; // human-readable, safe to display
  field?: string; // present for field-level validation errors
  details?: unknown; // structured extra context, optional
}

export interface ApiError {
  success: false;
  error: ApiErrorDetail;
  meta: ApiMeta;
}

export type ApiResponse<T> = ApiSuccess<T> | ApiError;

export function isApiSuccess<T>(res: ApiResponse<T>): res is ApiSuccess<T> {
  return res.success === true;
}
