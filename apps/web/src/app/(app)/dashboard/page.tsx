"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { useAuth } from "@/contexts/AuthContext";

/**
 * Placeholder protected page proving the auth flow end-to-end. Real
 * dashboard content arrives with the first business-feature module.
 * middleware.ts already redirects here-bound requests lacking a session
 * cookie; this client-side check additionally handles the case where the
 * cookie was present but the silent refresh (AuthContext bootstrap)
 * determined the session is actually invalid/expired.
 */
export default function DashboardPage() {
  const { user, status, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.push("/login?next=/dashboard");
    }
  }, [status, router]);

  if (status === "loading") {
    return <main style={{ padding: "3rem" }}>Loading…</main>;
  }

  if (status === "unauthenticated" || !user) {
    return null; // redirect effect above is already firing
  }

  return (
    <main style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif", padding: "3rem" }}>
      <h1>Dashboard</h1>
      <p>
        Signed in as <strong>{user.full_name}</strong> ({user.email}) — role: {user.role}
      </p>
      <button onClick={() => logout().then(() => router.push("/login"))}>Log out</button>
    </main>
  );
}
