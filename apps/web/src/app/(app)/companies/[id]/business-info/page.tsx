"use client";

import type { BusinessInfoUpdateRequest, BusinessType, LegalEntityType } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getCompany } from "@/lib/companies";
import { getBusinessInfo, updateBusinessInfo } from "@/lib/company-verification";
import * as ui from "@/lib/ui-styles";

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

  if (auth.status === "loading" || !loaded) return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;
  if (loadError) {
    return (
      <main style={ui.page}>
        <p style={ui.errorText}>{loadError}</p>
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
    <main style={ui.page}>
      <p>
        <Link href={`/companies/${params.id}/verification`}>&larr; Back to verification</Link>
      </p>
      <h1>Business information</h1>
      {!canEdit && <p style={ui.mutedText}>You have view-only access.</p>}

      <form
        onSubmit={handleSave}
        style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 520, opacity: canEdit ? 1 : 0.6 }}
      >
        <fieldset disabled={!canEdit} style={{ border: "none", padding: 0, display: "contents" }}>
          <div style={ui.formField}>
            <label htmlFor="legal_entity_type">Legal entity type</label>
            <select
              id="legal_entity_type"
              style={ui.input}
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
            </select>
          </div>

          <div style={ui.formField}>
            <label htmlFor="business_type">Manufacturer or trader?</label>
            <select
              id="business_type"
              style={ui.input}
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
            </select>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input
              type="checkbox"
              checked={form.export_capable ?? false}
              onChange={(e) => setForm((f) => ({ ...f, export_capable: e.target.checked }))}
            />
            Export capable
          </label>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={ui.formField}>
              <label htmlFor="gst_number">GSTIN</label>
              <input
                id="gst_number"
                style={ui.input}
                value={form.gst_number ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, gst_number: e.target.value }))}
              />
            </div>
            <div style={ui.formField}>
              <label htmlFor="pan">PAN</label>
              <input
                id="pan"
                style={ui.input}
                value={form.pan ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, pan: e.target.value }))}
              />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={ui.formField}>
              <label htmlFor="cin">CIN</label>
              <input
                id="cin"
                style={ui.input}
                value={form.cin ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, cin: e.target.value }))}
              />
            </div>
            <div style={ui.formField}>
              <label htmlFor="msme_number">MSME number</label>
              <input
                id="msme_number"
                style={ui.input}
                value={form.msme_number ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, msme_number: e.target.value }))}
              />
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
            <div style={ui.formField}>
              <label htmlFor="iec_number">IEC number</label>
              <input
                id="iec_number"
                style={ui.input}
                value={form.iec_number ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, iec_number: e.target.value }))}
              />
            </div>
            <div style={ui.formField}>
              <label htmlFor="business_registration_date">Registration date</label>
              <input
                id="business_registration_date"
                type="date"
                style={ui.input}
                value={form.business_registration_date ?? ""}
                onChange={(e) => setForm((f) => ({ ...f, business_registration_date: e.target.value }))}
              />
            </div>
          </div>

          <div style={ui.formField}>
            <label htmlFor="short_description">Short description</label>
            <input
              id="short_description"
              style={ui.input}
              maxLength={500}
              value={form.short_description ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, short_description: e.target.value }))}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="mission">Mission</label>
            <textarea
              id="mission"
              rows={2}
              style={ui.input}
              value={form.mission ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, mission: e.target.value }))}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="vision">Vision</label>
            <textarea
              id="vision"
              rows={2}
              style={ui.input}
              value={form.vision ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, vision: e.target.value }))}
            />
          </div>

          {saveError && <p style={ui.errorText}>{saveError}</p>}
          {saved && <p style={{ color: "#1a7f37" }}>Saved.</p>}

          <button type="submit" disabled={saving} style={ui.button}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </fieldset>
      </form>
    </main>
  );
}
