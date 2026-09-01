"use client";

import type { CompanyDetail, CompanyUpdateRequest } from "@platform/shared-types";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PageLoading } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { deleteCompany, getCompany, updateCompany } from "@/lib/companies";

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

  if (auth.status === "loading") return <PageLoading />;
  if (auth.status === "unauthenticated") return null;
  if (loadError) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <p className="text-sm text-danger">{loadError}</p>
      </main>
    );
  }
  if (!company) return <PageLoading />;

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
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p>
        <Link href={`/companies/${params.id}`} className="text-sm text-accent hover:text-accent-hover">
          &larr; Back to dashboard
        </Link>
      </p>
      <h1 className="mt-2 font-display text-xl font-semibold text-ink">Company settings</h1>

      {!canEdit && <p className="mt-1 text-sm text-ink-muted">You have view-only access to this company&apos;s settings.</p>}

      <form
        onSubmit={handleSave}
        className="mt-6 flex max-w-[520px] flex-col gap-4"
        style={{ opacity: canEdit ? 1 : 0.6 }}
      >
        <fieldset disabled={!canEdit} className="contents border-none p-0">
          <Input
            label="Company name"
            id="name"
            value={form.name ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
          />
          <Input
            label={
              company.my_role === "editor" ? (
                <>
                  Legal name <span className="text-ink-muted">(Admin/Owner only)</span>
                </>
              ) : (
                "Legal name"
              )
            }
            id="legal_name"
            disabled={company.my_role === "editor"}
            value={form.legal_name ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, legal_name: e.target.value }))}
          />
          <Textarea
            label="Description"
            id="description"
            rows={3}
            value={form.description ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
          />
          <Input
            label="Industry"
            id="industry"
            value={form.industry ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, industry: e.target.value }))}
          />
          <Input
            label="Website"
            id="website"
            value={form.website ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))}
          />

          {saveError && <p className="text-sm text-danger">{saveError}</p>}
          {saved && <p className="text-sm text-success">Saved.</p>}

          <Button type="submit" disabled={saving} className="self-start">
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </fieldset>
      </form>

      <hr className="my-10 border-t border-border" />

      <section>
        <h2 className="font-display text-lg font-semibold text-ink">Transfer ownership</h2>
        <p className="mt-2 text-sm text-ink-muted">
          Ownership transfer is available via the API (
          <code className="font-mono text-xs">PATCH /companies/{"{id}"}/members/{"{member}"}</code> with{" "}
          <code className="font-mono text-xs">role: &quot;owner&quot;</code>) — see{" "}
          <code className="font-mono text-xs">docs/adr/0024-ownership-transfer-mechanism.md</code>. A full
          member-picker UI for this is out of Module 3A&apos;s scope; this placeholder confirms the settings page
          has a home for it.
        </p>
        <Button type="button" variant="secondary" disabled className="mt-3 cursor-not-allowed">
          Transfer ownership (coming soon)
        </Button>
      </section>

      {canDelete && (
        <section className="mt-10">
          <h2 className="font-display text-lg font-semibold text-ink">Danger zone</h2>
          {!confirmingDelete ? (
            <Button type="button" variant="danger" className="mt-3" onClick={() => setConfirmingDelete(true)}>
              Delete company
            </Button>
          ) : (
            <div className="mt-3 rounded-lg border border-danger bg-canvas p-5">
              <p className="text-sm text-ink">
                This archives <strong>{company.name}</strong>. It will no longer appear in search or be
                accessible via its public profile. This cannot be undone from the UI.
              </p>
              <div className="mt-3 flex gap-3">
                <Button type="button" variant="danger" disabled={deleting} onClick={handleDelete}>
                  {deleting ? "Deleting…" : "Confirm delete"}
                </Button>
                <Button type="button" variant="secondary" onClick={() => setConfirmingDelete(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
