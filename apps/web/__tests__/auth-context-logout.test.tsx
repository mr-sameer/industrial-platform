import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";

const loggerErrorMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/logger", () => ({
  logger: { error: loggerErrorMock, info: vi.fn(), warn: vi.fn() },
}));

/**
 * Regression coverage for the confirmed audit bug: POST /api/auth/logout
 * returns HTTP 204 with no body, but the old postJson() unconditionally
 * called res.json() on every response, throwing
 * "SyntaxError: Unexpected end of JSON input" — which, left uncaught,
 * aborted logout() before it reached clearSession(), so the UI kept
 * showing the signed-in state (with a stray error toast) even though
 * the server-side session had actually already been invalidated.
 *
 * These tests use a real fetch mock rather than mocking postJson
 * directly, so a regression in the actual 204-handling logic — not just
 * in some test double standing in for it — would be caught.
 */

function Probe() {
  const { status, logout } = useAuth();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <button onClick={() => void logout()}>Log out</button>
    </div>
  );
}

function jsonResponse(body: unknown, status = 200) {
  return {
    status,
    text: async () => JSON.stringify(body),
    json: async () => body,
  };
}

/** A real 204's .json() throws exactly like the browser's Fetch API does — this is the regression itself if postJson ever calls it again. */
function noBodyResponse(status = 204) {
  return {
    status,
    text: async () => "",
    json: async () => {
      throw new SyntaxError("Unexpected end of JSON input");
    },
  };
}

const sessionUser = {
  id: "u1",
  email: "buyer@example.com",
  full_name: "Test Buyer",
  role: "viewer" as const,
  is_active: true,
  is_email_verified: true,
  created_at: "2026-01-01T00:00:00Z",
};

async function renderAuthenticated() {
  const fetchMock = vi.fn().mockImplementation((path: string) => {
    if (path === "/api/auth/refresh") {
      return Promise.resolve(
        jsonResponse({
          success: true,
          data: { access_token: "token-abc", expires_in_minutes: 15, user: sessionUser },
          meta: { requestId: "x", timestamp: "now" },
        })
      );
    }
    throw new Error(`unexpected fetch to ${path}`);
  });
  vi.stubGlobal("fetch", fetchMock);

  render(
    <AuthProvider>
      <Probe />
    </AuthProvider>
  );
  await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("authenticated"));
  return fetchMock;
}

describe("AuthContext logout", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    loggerErrorMock.mockClear();
  });

  it("clears the session on a successful 204 logout without throwing", async () => {
    const fetchMock = await renderAuthenticated();
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/auth/logout") return Promise.resolve(noBodyResponse(204));
      throw new Error(`unexpected fetch to ${path}`);
    });

    fireEvent.click(screen.getByText("Log out"));

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    // No false error logged on the successful path — this is the
    // regression itself: res.json() throwing on the 204's empty body
    // used to abort before clearSession() ever ran.
    expect(loggerErrorMock).not.toHaveBeenCalled();
  });

  it("still clears the session when the logout request itself fails — best-effort, matching logoutAll's existing behavior", async () => {
    const fetchMock = await renderAuthenticated();
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/auth/logout") return Promise.reject(new Error("network down"));
      throw new Error(`unexpected fetch to ${path}`);
    });

    fireEvent.click(screen.getByText("Log out"));

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    // A real failure is still logged (honest), just never left uncaught.
    expect(loggerErrorMock).toHaveBeenCalled();
  });

  it("a real malformed-JSON error response is still handled without crashing the app", async () => {
    const fetchMock = await renderAuthenticated();
    fetchMock.mockImplementation((path: string) => {
      if (path === "/api/auth/logout") {
        return Promise.resolve({
          status: 500,
          json: async () => {
            throw new SyntaxError("Unexpected token");
          },
        });
      }
      throw new Error(`unexpected fetch to ${path}`);
    });

    fireEvent.click(screen.getByText("Log out"));

    // Still resolves out of the click handler and clears local state
    // rather than leaving the UI stuck showing "authenticated".
    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("unauthenticated"));
    expect(loggerErrorMock).toHaveBeenCalled();
  });
});
