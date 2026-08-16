"use client";

import { CheckCircle2, XCircle } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AuthCard } from "@/components/auth/AuthCard";
import { Button } from "@/components/ui/Button";

type Status = "verifying" | "success" | "error";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>("verifying");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("This link is missing its verification token.");
      return;
    }
    let cancelled = false;
    fetch("/api/auth/verify-email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
      .then(async (res) => {
        if (cancelled) return;
        if (res.ok) {
          setStatus("success");
        } else {
          const body = (await res.json()) as { error: { message: string } };
          setStatus("error");
          setMessage(body.error.message);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("error");
          setMessage("Something went wrong. Please try again.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "verifying") {
    return (
      <AuthCard title="Verifying your email…" subtitle="This will only take a moment." footer={null}>
        <div className="flex justify-center py-4">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-border border-t-accent" />
        </div>
      </AuthCard>
    );
  }

  if (status === "success") {
    return (
      <AuthCard
        title="Email verified"
        subtitle="Your email address has been confirmed."
        footer={
          <Link href="/login" className="font-medium text-accent hover:text-accent-hover">
            Log in
          </Link>
        }
      >
        <div className="flex flex-col items-center gap-3 py-2 text-center">
          <CheckCircle2 size={40} className="text-success" aria-hidden />
          <Button asChild className="mt-2 w-full">
            <Link href="/login">Continue to log in</Link>
          </Button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Verification failed"
      subtitle={message ?? "That verification link is invalid or has expired."}
      footer={
        <Link href="/login" className="font-medium text-accent hover:text-accent-hover">
          Back to log in
        </Link>
      }
    >
      <div className="flex flex-col items-center gap-3 py-2 text-center">
        <XCircle size={40} className="text-danger" aria-hidden />
      </div>
    </AuthCard>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
