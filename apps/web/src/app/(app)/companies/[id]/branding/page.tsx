"use client";

import type { CompanyBrandingPublic } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import {
  deleteCoverImage,
  deleteLogo,
  getBranding,
  uploadCoverImage,
  uploadLogo,
} from "@/lib/company-verification";
import * as ui from "@/lib/ui-styles";

/** Company Branding — Module 3B. Logo and cover image upload/replace/delete. */
export default function BrandingPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/branding`);
  const [branding, setBranding] = useState<CompanyBrandingPublic | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);
  const [coverUploading, setCoverUploading] = useState(false);
  const logoInputRef = useRef<HTMLInputElement>(null);
  const coverInputRef = useRef<HTMLInputElement>(null);

  const fetchInitialState = useCallback(async () => {
    if (!auth.accessToken) return;
    const result = await getBranding(params.id, auth.accessToken);
    if (result.success) {
      setBranding(result.data);
    } else {
      setError(result.error.message);
    }
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchInitialState();
  }, [auth.status, fetchInitialState]);

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  async function handleLogoUpload() {
    const file = logoInputRef.current?.files?.[0];
    if (!file || !auth.accessToken) return;
    setLogoUploading(true);
    setError(null);
    const result = await uploadLogo(params.id, file, auth.accessToken);
    setLogoUploading(false);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    setBranding(result.data);
  }

  async function handleLogoDelete() {
    if (!auth.accessToken) return;
    const result = await deleteLogo(params.id, auth.accessToken);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    setBranding((prev) => (prev ? { ...prev, logo_url: null, logo_thumbnail_url: null } : prev));
  }

  async function handleCoverUpload() {
    const file = coverInputRef.current?.files?.[0];
    if (!file || !auth.accessToken) return;
    setCoverUploading(true);
    setError(null);
    const result = await uploadCoverImage(params.id, file, auth.accessToken);
    setCoverUploading(false);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    setBranding((prev) => (prev ? { ...prev, cover_image_url: result.data.cover_image_url } : result.data));
  }

  async function handleCoverDelete() {
    if (!auth.accessToken) return;
    const result = await deleteCoverImage(params.id, auth.accessToken);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    setBranding((prev) => (prev ? { ...prev, cover_image_url: null } : prev));
  }

  return (
    <main style={ui.page}>
      <p>
        <Link href={`/companies/${params.id}/verification`}>&larr; Back to verification</Link>
      </p>
      <h1>Branding</h1>
      {error && <p style={ui.errorText}>{error}</p>}

      <div style={{ ...ui.cardGrid }}>
        <div style={ui.card}>
          <h3 style={{ marginTop: 0 }}>Logo</h3>
          {branding?.logo_thumbnail_url && (
            /* eslint-disable-next-line @next/next/no-img-element -- external/uploaded URL, not a static asset */
            <img
              src={branding.logo_thumbnail_url}
              alt="Company logo"
              width={96}
              height={96}
              style={{ borderRadius: 8, marginBottom: "0.75rem" }}
            />
          )}
          <input ref={logoInputRef} type="file" accept="image/jpeg,image/png,image/webp" />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
            <button type="button" style={ui.button} disabled={logoUploading} onClick={handleLogoUpload}>
              {logoUploading ? "Uploading…" : "Upload"}
            </button>
            {branding?.logo_url && (
              <button type="button" style={ui.buttonDanger} onClick={handleLogoDelete}>
                Delete
              </button>
            )}
          </div>
          <p style={ui.mutedText}>JPEG, PNG, or WEBP, up to 5 MB. A 256×256 thumbnail is generated automatically.</p>
        </div>

        <div style={ui.card}>
          <h3 style={{ marginTop: 0 }}>Cover image</h3>
          {branding?.cover_image_url && (
            /* eslint-disable-next-line @next/next/no-img-element -- external/uploaded URL, not a static asset */
            <img
              src={branding.cover_image_url}
              alt="Company cover"
              style={{ width: "100%", maxHeight: 120, objectFit: "cover", borderRadius: 8, marginBottom: "0.75rem" }}
            />
          )}
          <input ref={coverInputRef} type="file" accept="image/jpeg,image/png,image/webp" />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
            <button type="button" style={ui.button} disabled={coverUploading} onClick={handleCoverUpload}>
              {coverUploading ? "Uploading…" : "Upload"}
            </button>
            {branding?.cover_image_url && (
              <button type="button" style={ui.buttonDanger} onClick={handleCoverDelete}>
                Delete
              </button>
            )}
          </div>
          <p style={ui.mutedText}>JPEG, PNG, or WEBP, up to 10 MB. Responsive variants are generated automatically.</p>
        </div>
      </div>
    </main>
  );
}
