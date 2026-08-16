"use client";

import type { VerificationScorePublic } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";


import { VerificationProgress } from "@/components/VerificationProgress";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getVerification } from "@/lib/company-verification";
import * as ui from "@/lib/ui-styles";

/** Verification Dashboard — Module 3B. */
export default function VerificationDashboardPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/verification`);
  const [score, setScore] = useState<VerificationScorePublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchScore = useCallback(async () => {
    if (!auth.accessToken) return;
    setLoading(true);
    const result = await getVerification(params.id, auth.accessToken);
    if (result.success) {
      setScore(result.data);
    } else {
      setError(result.error.message);
    }
    setLoading(false);
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchScore();
  }, [auth.status, fetchScore]);

  if (auth.status === "loading" || loading) return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  return (
    <main style={ui.page}>
      <p>
        <Link href={`/companies/${params.id}`}>&larr; Back to dashboard</Link>
      </p>
      <h1>Verification</h1>

      {error && <p style={ui.errorText}>{error}</p>}
      {!error && !score && <p style={ui.mutedText}>Loading verification status…</p>}
      {score && <VerificationProgress score={score} />}

      <div style={{ ...ui.cardGrid, marginTop: "1.5rem" }}>
        <Link href={`/companies/${params.id}/business-info`} style={{ ...ui.card, textDecoration: "none", color: "inherit" }}>
          <h4 style={{ margin: 0 }}>Business Information</h4>
          <p style={ui.mutedText}>Legal entity, registration numbers, description</p>
        </Link>
        <Link href={`/companies/${params.id}/documents`} style={{ ...ui.card, textDecoration: "none", color: "inherit" }}>
          <h4 style={{ margin: 0 }}>Documents</h4>
          <p style={ui.mutedText}>Certificates and registration evidence</p>
        </Link>
        <Link href={`/companies/${params.id}/branding`} style={{ ...ui.card, textDecoration: "none", color: "inherit" }}>
          <h4 style={{ margin: 0 }}>Branding</h4>
          <p style={ui.mutedText}>Logo and cover image</p>
        </Link>
        <Link href={`/companies/${params.id}/social-links`} style={{ ...ui.card, textDecoration: "none", color: "inherit" }}>
          <h4 style={{ margin: 0 }}>Social Links</h4>
          <p style={ui.mutedText}>LinkedIn, YouTube, Facebook, Instagram, X</p>
        </Link>
      </div>
    </main>
  );
}
