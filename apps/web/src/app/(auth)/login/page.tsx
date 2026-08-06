"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { useAuth } from "@/contexts/AuthContext";

// useSearchParams() opts a page out of static rendering unless wrapped in
// Suspense — Next.js enforces this at build time (see
// https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
// The default export below is the Suspense wrapper; LoginForm holds the
// actual page content and is what reads the `?next=` redirect param.
export default function LoginPage() {
  return (
    <Suspense fallback={<main style={{ padding: "3rem" }}>Loading…</main>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const result = await login({ email, password });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push(searchParams.get("next") ?? "/dashboard");
  }

  return (
    <main style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif", padding: "3rem", maxWidth: 360 }}>
      <h1>Log in</h1>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <label>
          Email
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ display: "block", width: "100%" }}
          />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ display: "block", width: "100%" }}
          />
        </label>
        {error && <p style={{ color: "#cf222e" }}>{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Logging in…" : "Log in"}
        </button>
      </form>
      <p>
        No account? <a href="/register">Register</a>
      </p>
    </main>
  );
}
