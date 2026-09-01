"use client";

import type { SocialLinkPublic, SocialPlatform } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PageLoading } from "@/components/ui/Spinner";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { deleteSocialLink, listSocialLinks, upsertSocialLink } from "@/lib/company-verification";

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

  if (auth.status === "loading") return <PageLoading />;
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
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p>
        <Link href={`/companies/${params.id}/verification`} className="text-sm text-accent hover:text-accent-hover">
          &larr; Back to verification
        </Link>
      </p>
      <h1 className="mt-2 font-display text-xl font-semibold text-ink">Social links</h1>
      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      <div className="mt-6 flex max-w-[520px] flex-col gap-4">
        {PLATFORMS.map((platform) => (
          <div key={platform} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <Input
              label={PLATFORM_LABELS[platform]}
              id={platform}
              type="url"
              className="sm:flex-1"
              placeholder={`https://${platform}.com/...`}
              value={links[platform] ?? ""}
              onChange={(e) => setLinks((prev) => ({ ...prev, [platform]: e.target.value }))}
            />
            <div className="flex gap-2">
              <Button type="button" disabled={saving === platform} onClick={() => handleSave(platform)}>
                Save
              </Button>
              <Button type="button" variant="secondary" onClick={() => handleRemove(platform)}>
                Remove
              </Button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
