"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { AuthCard } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/contexts/AuthContext";

// useSearchParams() opts a page out of static rendering unless wrapped in
// Suspense — Next.js enforces this at build time (see
// https://nextjs.org/docs/messages/missing-suspense-with-csr-bailout).
// The default export below is the Suspense wrapper; LoginForm holds the
// actual page content and is what reads the `?next=` redirect param.
export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center bg-surface">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-border-strong border-t-accent" />
        </main>
      }
    >
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
  const justReset = searchParams.get("reset") === "success";

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
    <AuthCard
      title="Log in"
      subtitle="Welcome back — sign in to your account."
      footer={
        <>
          No account?{" "}
          <Link href="/register" className="font-medium text-accent hover:text-accent-hover">
            Register
          </Link>
        </>
      }
    >
      {justReset && (
        <p className="mb-4 rounded-md bg-success-subtle px-3 py-2 text-sm text-success">
          Your password has been reset. Log in with your new password.
        </p>
      )}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <Input
          label="Email"
          type="email"
          name="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          // Browsers' built-in autofill/password-manager heuristics can
          // mutate this element's style/attributes before React's
          // hydration check runs, causing a harmless false-positive
          // mismatch warning unrelated to this component's own
          // (deterministic) output — see docs/adr/0031.
          suppressHydrationWarning
        />
        <div>
          <Input
            label="Password"
            type="password"
            name="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            suppressHydrationWarning
          />
          <Link
            href="/forgot-password"
            className="mt-1.5 inline-block text-xs font-medium text-accent hover:text-accent-hover"
          >
            Forgot password?
          </Link>
        </div>
        {error && (
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
        )}
        <Button type="submit" disabled={submitting} className="mt-1 w-full">
          {submitting ? "Logging in…" : "Log in"}
        </Button>
      </form>
    </AuthCard>
  );
}
