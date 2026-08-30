"use client";

import type { BusinessInfoUpdateRequest, BusinessType, LegalEntityType } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { Textarea } from "@/components/ui/Textarea";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getCompany } from "@/lib/companies";
import { getBusinessInfo, updateBusinessInfo } from "@/lib/company-verification";

const LEGAL_ENTITY_TYPES: LegalEntityType[] = [
  "private_limited",
  "llp",
  "proprietorship",
  "partnership",
  "public_limited",
  "government",
  "ngo",
  "other",
];
const BUSINESS_TYPES: BusinessType[] = ["manufacturer", "trader", "both"];

/** Business Information — Module 3B. */
export default function BusinessInfoPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/business-info`);
  const [form, setForm] = useState<BusinessInfoUpdateRequest>({});
  const [canEdit, setCanEdit] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [loaded, setLoaded] = useState(false);

  const fetchCompany = useCallback(async () => {
    if (!auth.accessToken) return;
    const [companyResult, businessInfoResult] = await Promise.all([
      getCompany(params.id, auth.accessToken),
      getBusinessInfo(params.id, auth.accessToken),
    ]);
    if (!companyResult.success) {
      setLoadError(companyResult.error.message);
      setLoaded(true);
      return;
    }
    setCanEdit(
      companyResult.data.my_role === "owner" ||
        companyResult.data.my_role === "admin" ||
        companyResult.data.my_role === "editor"
    );
    if (businessInfoResult.success) {
      setForm(businessInfoResult.data);
    } else {
      setLoadError(businessInfoResult.error.message);
    }
    setLoaded(true);
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchCompany();
  }, [auth.status, fetchCompany]);

  if (auth.status === "loading" || !loaded) return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;
  if (loadError) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <p className="text-sm text-danger">{loadError}</p>
      </main>
    );
  }

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!auth.accessToken) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    const result = await updateBusinessInfo(params.id, form, auth.accessToken);
    setSaving(false);
    if (!result.success) {
      setSaveError(result.error.message);
      return;
    }
    setSaved(true);
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p>
        <Link href={`/companies/${params.id}/verification`} className="text-sm text-accent hover:text-accent-hover">
          &larr; Back to verification
        </Link>
      </p>
      <h1 className="mt-2 font-display text-xl font-semibold text-ink">Business information</h1>
      {!canEdit && <p className="mt-1 text-sm text-ink-muted">You have view-only access.</p>}

      <form
        onSubmit={handleSave}
        className="mt-6 flex max-w-[520px] flex-col gap-4"
        style={{ opacity: canEdit ? 1 : 0.6 }}
      >
        <fieldset disabled={!canEdit} className="contents border-none p-0">
          <Select
            label="Legal entity type"
            id="legal_entity_type"
            value={form.legal_entity_type ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, legal_entity_type: (e.target.value || undefined) as LegalEntityType | undefined }))
            }
          >
            <option value="">Select…</option>
            {LEGAL_ENTITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </Select>

          <Select
            label="Manufacturer or trader?"
            id="business_type"
            value={form.business_type ?? ""}
            onChange={(e) =>
              setForm((f) => ({ ...f, business_type: (e.target.value || undefined) as BusinessType | undefined }))
            }
          >
            <option value="">Select…</option>
            {BUSINESS_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>

          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-border-strong accent-accent"
              checked={form.export_capable ?? false}
              onChange={(e) => setForm((f) => ({ ...f, export_capable: e.target.checked }))}
            />
            Export capable
          </label>

          {/* IBM Plex Mono for GSTIN/PAN/CIN/MSME/IEC values, per docs/architecture/design-system.md. */}
          <div>
            <h2 className="text-sm font-semibold text-ink">Registration identifiers</h2>
            {/* Mirrors the real verification weighting (verification_rules.py's
                government_id_set requirement): GSTIN/PAN/CIN satisfy the same
                one-of-three check toward Business Verified, while MSME and IEC
                carry no verification weight at all — not equally important,
                whatever the plain-field layout below implies on its own. */}
            <p className="mt-1 text-xs text-ink-muted">
              At least one government ID — GSTIN, PAN, or CIN — is required to reach Business
              Verified. MSME and IEC numbers are optional and used for export/trade context.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={
                <span className="inline-flex items-center gap-1.5">
                  GSTIN <Badge variant="accent">One required</Badge>
                </span>
              }
              id="gst_number"
              className="font-mono"
              value={form.gst_number ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, gst_number: e.target.value }))}
            />
            <Input
              label={
                <span className="inline-flex items-center gap-1.5">
                  PAN <Badge variant="accent">One required</Badge>
                </span>
              }
              id="pan"
              className="font-mono"
              value={form.pan ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, pan: e.target.value }))}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={
                <span className="inline-flex items-center gap-1.5">
                  CIN <Badge variant="accent">One required</Badge>
                </span>
              }
              id="cin"
              className="font-mono"
              value={form.cin ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, cin: e.target.value }))}
            />
            <Input
              label={
                <span className="inline-flex items-center gap-1.5">
                  MSME number <Badge variant="neutral">Optional</Badge>
                </span>
              }
              id="msme_number"
              className="font-mono"
              value={form.msme_number ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, msme_number: e.target.value }))}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={
                <span className="inline-flex items-center gap-1.5">
                  IEC number <Badge variant="neutral">Optional</Badge>
                </span>
              }
              id="iec_number"
              className="font-mono"
              value={form.iec_number ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, iec_number: e.target.value }))}
            />
            <Input
              label="Registration date"
              id="business_registration_date"
              type="date"
              value={form.business_registration_date ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, business_registration_date: e.target.value }))}
            />
          </div>

          <Input
            label="Short description"
            id="short_description"
            maxLength={500}
            value={form.short_description ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, short_description: e.target.value }))}
          />
          <Textarea
            label="Mission"
            id="mission"
            rows={2}
            value={form.mission ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, mission: e.target.value }))}
          />
          <Textarea
            label="Vision"
            id="vision"
            rows={2}
            value={form.vision ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, vision: e.target.value }))}
          />

          {saveError && <p className="text-sm text-danger">{saveError}</p>}
          {saved && <p className="text-sm text-success">Saved.</p>}

          <Button type="submit" disabled={saving} className="self-start">
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </fieldset>
      </form>
    </main>
  );
}
