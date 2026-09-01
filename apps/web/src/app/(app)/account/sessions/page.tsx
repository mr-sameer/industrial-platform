"use client";

import type { ApiResponse, SessionPublic } from "@platform/shared-types";
import { useCallback, useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { PageLoading } from "@/components/ui/Spinner";
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

  if (status === "loading") return <PageLoading />;
  if (status === "unauthenticated") {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <p className="text-sm text-ink-muted">
          Please{" "}
          <a href="/login?next=/account/sessions" className="text-accent hover:text-accent-hover">
            log in
          </a>{" "}
          to view your sessions.
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-xl font-semibold text-ink">Active sessions</h1>
      <p className="mt-1 text-sm text-ink-muted">These are the devices currently signed in to your account.</p>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {sessions === null && !error && <p className="mt-4 text-sm text-ink-muted">Loading sessions…</p>}

      {sessions && sessions.length > 0 && (
        <div className="mt-6 flex flex-col gap-3">
          {sessions.map((s) => (
            <div
              key={s.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-canvas p-4"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <p className="truncate text-sm font-medium text-ink">
                    {s.device_name ?? s.browser ?? "Unknown device"}
                  </p>
                  {s.is_current && <Badge variant="accent">This device</Badge>}
                </div>
                <p className="mt-1 text-xs text-ink-muted">
                  {s.platform ?? "Unknown platform"} · {s.ip_address ?? "unknown IP"}
                </p>
                <p className="mt-0.5 text-xs text-ink-faint">
                  Last active {new Date(s.last_active_at).toLocaleString()}
                </p>
              </div>
              {!s.is_current && (
                <Button type="button" variant="secondary" size="sm" onClick={() => revoke(s.id)}>
                  Revoke
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      <Button type="button" variant="danger" className="mt-6" onClick={() => logoutAll()}>
        Log out everywhere
      </Button>
    </main>
  );
}
