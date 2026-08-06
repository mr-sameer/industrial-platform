"use client";

import type { CompanyDetail, CompanyUpdateRequest } from "@platform/shared-types";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { deleteCompany, getCompany, updateCompany } from "@/lib/companies";
import * as ui from "@/lib/ui-styles";

/**
 * Company Settings — Module 3A. Edit profile, delete company, and a
 * transfer-ownership placeholder (per this module's brief — the real
 * transfer mechanism already exists at the API level, see
 * docs/adr/0024-ownership-transfer-mechanism.md; this page only surfaces
 * a disabled/placeholder control, not a working member picker, since a
 * full member-management UI is out of this module's explicit scope).
 */
export default function CompanySettingsPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/settings`);
  const router = useRouter();
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [form, setForm] = useState<CompanyUpdateRequest>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  const fetchCompany = useCallback(async () => {
    if (!auth.accessToken) return;
    const result = await getCompany(params.id, auth.accessToken);
    if (result.success) {
      setCompany(result.data);
      setForm({
        name: result.data.name,
        legal_name: result.data.legal_name,
        description: result.data.description ?? "",
        industry: result.data.industry ?? "",
        website: result.data.website ?? "",
        email: result.data.email ?? "",
        phone: result.data.phone ?? "",
        country: result.data.country ?? "",
        state: result.data.state ?? "",
        city: result.data.city ?? "",
      });
    } else {
      setLoadError(result.error.message);
    }
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchCompany();
  }, [auth.status, fetchCompany]);

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;
  if (loadError) {
    return (
      <main style={ui.page}>
        <p style={ui.errorText}>{loadError}</p>
      </main>
    );
  }
  if (!company) return <main style={ui.page}>Loading…</main>;

  const canEdit = company.my_role === "owner" || company.my_role === "admin" || company.my_role === "editor";
  const canDelete = company.my_role === "owner";

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    if (!auth.accessToken) return;
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    const result = await updateCompany(params.id, form, auth.accessToken);
    setSaving(false);
    if (!result.success) {
      setSaveError(result.error.message);
      return;
    }
    setCompany(result.data);
    setSaved(true);
  }

  async function handleDelete() {
    if (!auth.accessToken) return;
    setDeleting(true);
    const result = await deleteCompany(params.id, auth.accessToken);
    setDeleting(false);
    if (result.success) {
      router.push("/companies");
    } else {
      setSaveError(result.error.message);
    }
  }

  return (
    <main style={ui.page}>
      <p>
        <Link href={`/companies/${params.id}`}>&larr; Back to dashboard</Link>
      </p>
      <h1>Company settings</h1>

      {!canEdit && <p style={ui.mutedText}>You have view-only access to this company&apos;s settings.</p>}

      <form
        onSubmit={handleSave}
        style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 520, opacity: canEdit ? 1 : 0.6 }}
      >
        <fieldset disabled={!canEdit} style={{ border: "none", padding: 0, display: "contents" }}>
          <div style={ui.formField}>
            <label htmlFor="name">Company name</label>
            <input
              id="name"
              style={ui.input}
              value={form.name ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="legal_name">
              Legal name {company.my_role === "editor" && <span style={ui.mutedText}>(Admin/Owner only)</span>}
            </label>
            <input
              id="legal_name"
              disabled={company.my_role === "editor"}
              style={ui.input}
              value={form.legal_name ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, legal_name: e.target.value }))}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="description">Description</label>
            <textarea
              id="description"
              rows={3}
              style={ui.input}
              value={form.description ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="industry">Industry</label>
            <input
              id="industry"
              style={ui.input}
              value={form.industry ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="website">Website</label>
            <input
              id="website"
              style={ui.input}
              value={form.website ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))}
            />
          </div>

          {saveError && <p style={ui.errorText}>{saveError}</p>}
          {saved && <p style={{ color: "#1a7f37" }}>Saved.</p>}

          <button type="submit" disabled={saving} style={ui.button}>
            {saving ? "Saving…" : "Save changes"}
          </button>
        </fieldset>
      </form>

      <hr style={{ margin: "2.5rem 0", border: "none", borderTop: "1px solid #eee" }} />

      <section>
        <h2>Transfer ownership</h2>
        <p style={ui.mutedText}>
          Ownership transfer is available via the API (
          <code>PATCH /companies/{"{id}"}/members/{"{member}"}</code> with <code>role: &quot;owner&quot;</code>) —
          see <code>docs/adr/0024-ownership-transfer-mechanism.md</code>. A full member-picker UI for this is
          out of Module 3A&apos;s scope; this placeholder confirms the settings page has a home for it.
        </p>
        <button type="button" disabled style={{ ...ui.buttonSecondary, cursor: "not-allowed" }}>
          Transfer ownership (coming soon)
        </button>
      </section>

      {canDelete && (
        <section style={{ marginTop: "2.5rem" }}>
          <h2>Danger zone</h2>
          {!confirmingDelete ? (
            <button type="button" style={ui.buttonDanger} onClick={() => setConfirmingDelete(true)}>
              Delete company
            </button>
          ) : (
            <div style={{ ...ui.card, borderColor: "#cf222e" }}>
              <p>
                This archives <strong>{company.name}</strong>. It will no longer appear in search or be
                accessible via its public profile. This cannot be undone from the UI.
              </p>
              <div style={{ display: "flex", gap: "0.75rem" }}>
                <button type="button" style={ui.buttonDanger} disabled={deleting} onClick={handleDelete}>
                  {deleting ? "Deleting…" : "Confirm delete"}
                </button>
                <button type="button" style={ui.buttonSecondary} onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
