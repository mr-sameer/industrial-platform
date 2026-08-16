"use client";

import type { SocialLinkPublic, SocialPlatform } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { deleteSocialLink, listSocialLinks, upsertSocialLink } from "@/lib/company-verification";
import * as ui from "@/lib/ui-styles";

const PLATFORMS: SocialPlatform[] = ["linkedin", "youtube", "facebook", "instagram", "x"];
const PLATFORM_LABELS: Record<SocialPlatform, string> = {
  linkedin: "LinkedIn",
  youtube: "YouTube",
  facebook: "Facebook",
  instagram: "Instagram",
  x: "X",
};

/** Social Links — Module 3B. Website itself is Module 3A's existing field, edited on the Settings page. */
export default function SocialLinksPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/social-links`);
  const [links, setLinks] = useState<Record<SocialPlatform, string>>({} as Record<SocialPlatform, string>);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<SocialPlatform | null>(null);

  const fetchLinks = useCallback(async () => {
    if (!auth.accessToken) return;
    const result = await listSocialLinks(params.id, auth.accessToken);
    if (result.success) {
      const map: Record<string, string> = {};
      for (const link of result.data as SocialLinkPublic[]) map[link.platform] = link.url;
      setLinks(map as Record<SocialPlatform, string>);
    } else {
      setError(result.error.message);
    }
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchLinks();
  }, [auth.status, fetchLinks]);

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  async function handleSave(platform: SocialPlatform) {
    if (!auth.accessToken) return;
    const url = links[platform];
    if (!url) return;
    setSaving(platform);
    setError(null);
    const result = await upsertSocialLink(params.id, platform, url, auth.accessToken);
    setSaving(null);
    if (!result.success) {
      setError(result.error.message);
    }
  }

  async function handleRemove(platform: SocialPlatform) {
    if (!auth.accessToken) return;
    const result = await deleteSocialLink(params.id, platform, auth.accessToken);
    if (!result.success && result.error.code !== "SOCIAL_LINK_NOT_FOUND") {
      setError(result.error.message);
      return;
    }
    setLinks((prev) => ({ ...prev, [platform]: "" }));
  }

  return (
    <main style={ui.page}>
      <p>
        <Link href={`/companies/${params.id}/verification`}>&larr; Back to verification</Link>
      </p>
      <h1>Social links</h1>
      {error && <p style={ui.errorText}>{error}</p>}

      <div style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 520 }}>
        {PLATFORMS.map((platform) => (
          <div key={platform} style={ui.formField}>
            <label htmlFor={platform}>{PLATFORM_LABELS[platform]}</label>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <input
                id={platform}
                type="url"
                style={ui.input}
                placeholder={`https://${platform}.com/...`}
                value={links[platform] ?? ""}
                onChange={(e) => setLinks((prev) => ({ ...prev, [platform]: e.target.value }))}
              />
              <button
                type="button"
                style={ui.button}
                disabled={saving === platform}
                onClick={() => handleSave(platform)}
              >
                Save
              </button>
              <button type="button" style={ui.buttonSecondary} onClick={() => handleRemove(platform)}>
                Remove
              </button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
