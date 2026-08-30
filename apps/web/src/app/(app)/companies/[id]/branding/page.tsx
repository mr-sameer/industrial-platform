"use client";

import type { CompanyBrandingPublic } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import {
  deleteCoverImage,
  deleteLogo,
  getBranding,
  uploadCoverImage,
  uploadLogo,
} from "@/lib/company-verification";

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

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
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
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p>
        <Link href={`/companies/${params.id}/verification`} className="text-sm text-accent hover:text-accent-hover">
          &larr; Back to verification
        </Link>
      </p>
      <h1 className="mt-2 font-display text-xl font-semibold text-ink">Branding</h1>
      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      <div className="mt-6 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
        <div className="rounded-lg border border-border bg-canvas p-5">
          <h3 className="text-sm font-semibold text-ink">Logo</h3>
          {branding?.logo_thumbnail_url && (
            /* eslint-disable-next-line @next/next/no-img-element -- external/uploaded URL, not a static asset */
            <img
              src={branding.logo_thumbnail_url}
              alt="Company logo"
              width={96}
              height={96}
              className="mt-3 rounded-lg"
            />
          )}
          <input ref={logoInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="mt-3 text-sm text-ink-muted" />
          <div className="mt-3 flex gap-2">
            <Button type="button" disabled={logoUploading} onClick={handleLogoUpload}>
              {logoUploading ? "Uploading…" : "Upload"}
            </Button>
            {branding?.logo_url && (
              <Button type="button" variant="danger" onClick={handleLogoDelete}>
                Delete
              </Button>
            )}
          </div>
          <p className="mt-2 text-sm text-ink-muted">JPEG, PNG, or WEBP, up to 5 MB. A 256×256 thumbnail is generated automatically.</p>
        </div>

        <div className="rounded-lg border border-border bg-canvas p-5">
          <h3 className="text-sm font-semibold text-ink">Cover image</h3>
          {branding?.cover_image_url && (
            /* eslint-disable-next-line @next/next/no-img-element -- external/uploaded URL, not a static asset */
            <img
              src={branding.cover_image_url}
              alt="Company cover"
              className="mt-3 max-h-[120px] w-full rounded-lg object-cover"
            />
          )}
          <input ref={coverInputRef} type="file" accept="image/jpeg,image/png,image/webp" className="mt-3 text-sm text-ink-muted" />
          <div className="mt-3 flex gap-2">
            <Button type="button" disabled={coverUploading} onClick={handleCoverUpload}>
              {coverUploading ? "Uploading…" : "Upload"}
            </Button>
            {branding?.cover_image_url && (
              <Button type="button" variant="danger" onClick={handleCoverDelete}>
                Delete
              </Button>
            )}
          </div>
          <p className="mt-2 text-sm text-ink-muted">JPEG, PNG, or WEBP, up to 10 MB. Responsive variants are generated automatically.</p>
        </div>
      </div>
    </main>
  );
}
