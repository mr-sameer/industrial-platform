"use client";

import type { ApiResponse, SessionPublic } from "@platform/shared-types";
import { useCallback, useEffect, useState } from "react";


import { useAuth } from "@/contexts/AuthContext";

/**
 * "Your active sessions" — Module 2.5 Phase 3's requirement that users
 * can see and revoke their own sessions. Not behind middleware.ts's
 * PROTECTED_PREFIXES yet (see docs/adr/0012) since that list is
 * currently /dashboard-only; this page checks auth client-side instead,
 * same pattern as the dashboard placeholder.
 */
export default function SessionsPage() {
  const { accessToken, status, logoutAll } = useAuth();
  const [sessions, setSessions] = useState<SessionPublic[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    if (!accessToken) return;
    const res = await fetch("/api/auth/sessions", {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const result = (await res.json()) as ApiResponse<SessionPublic[]>;
    if (result.success) {
      setSessions(result.data);
    } else {
      setError(result.error.message);
    }
  }, [accessToken]);

  useEffect(() => {
    if (status === "authenticated") fetchSessions();
  }, [status, fetchSessions]);

  async function revoke(sessionId: string) {
    if (!accessToken) return;
    await fetch(`/api/auth/sessions/${sessionId}`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    fetchSessions();
  }

  if (status === "loading") return <main style={{ padding: "3rem" }}>Loading…</main>;
  if (status === "unauthenticated") {
    return (
      <main style={{ padding: "3rem" }}>
        Please <a href="/login?next=/account/sessions">log in</a> to view your sessions.
      </main>
    );
  }

  return (
    <main style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif", padding: "3rem", maxWidth: 640 }}>
      <h1>Active sessions</h1>
      <p>These are the devices currently signed in to your account.</p>
      {error && <p style={{ color: "#cf222e" }}>{error}</p>}
      {sessions === null && !error && <p>Loading sessions…</p>}
      {sessions && (
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "1rem" }}>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #ddd" }}>
                <td style={{ padding: "0.75rem 0" }}>
                  <strong>
                    {s.device_name ?? s.browser ?? "Unknown device"}
                    {s.is_current ? " (this device)" : ""}
                  </strong>
                  <div style={{ color: "#666", fontSize: "0.85rem" }}>
                    {s.platform ?? "Unknown platform"} · {s.ip_address ?? "unknown IP"}
                    <br />
                    Last active {new Date(s.last_active_at).toLocaleString()}
                  </div>
                </td>
                <td style={{ textAlign: "right" }}>
                  {!s.is_current && <button onClick={() => revoke(s.id)}>Revoke</button>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <button style={{ marginTop: "1.5rem" }} onClick={() => logoutAll()}>
        Log out everywhere
      </button>
    </main>
  );
}
