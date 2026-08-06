"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/contexts/AuthContext";

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    const result = await register({ email, password, full_name: fullName });
    setSubmitting(false);
    if (!result.ok) {
      setError(result.message);
      return;
    }
    router.push("/dashboard");
  }

  return (
    <main style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif", padding: "3rem", maxWidth: 360 }}>
      <h1>Create an account</h1>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
        <label>
          Full name
          <input
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            style={{ display: "block", width: "100%" }}
          />
        </label>
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
            minLength={10}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ display: "block", width: "100%" }}
          />
          <small>At least 10 characters, with a letter and a digit.</small>
        </label>
        {error && <p style={{ color: "#cf222e" }}>{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p>
        Already have an account? <a href="/login">Log in</a>
      </p>
    </main>
  );
}
