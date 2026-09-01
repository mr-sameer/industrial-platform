"use client";

import type { CompanyCreateRequest, CompanySize } from "@platform/shared-types";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Select } from "@/components/ui/Select";
import { PageLoading } from "@/components/ui/Spinner";
import { Textarea } from "@/components/ui/Textarea";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { createCompany } from "@/lib/companies";

const COMPANY_SIZES: CompanySize[] = ["1-10", "11-50", "51-200", "201-1000", "1000+"];

const EMPTY_FORM: CompanyCreateRequest = {
  name: "",
  legal_name: "",
  description: "",
  industry: "",
  website: "",
  email: "",
  phone: "",
  year_established: undefined,
  company_size: undefined,
  gst_number: "",
  country: "",
  state: "",
  city: "",
};

/** "Create Company" — Module 3A. Requires a verified email (enforced server-side; see docs/adr's Phase 4 note). */
export default function CreateCompanyPage() {
  const auth = useRequireAuth("/companies/new");
  const router = useRouter();
  const [form, setForm] = useState<CompanyCreateRequest>(EMPTY_FORM);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  if (auth.status === "loading") return <PageLoading />;
  if (auth.status === "unauthenticated") return null;

  // ForgeX Product Audit P1: this requirement was previously only
  // enforced server-side (see this file's own top-of-file comment),
  // which meant a buyer only learned about it as a small line below
  // the fold after filling out the entire form and submitting. Since
  // `is_email_verified` is already on the session user (no extra
  // request needed), surface the same requirement up front instead.
  if (auth.user && !auth.user.is_email_verified) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <h1 className="font-display text-xl font-semibold text-ink">Create a company</h1>
        <div className="mt-4 max-w-[520px] rounded-lg border border-border bg-canvas p-5">
          <p className="text-sm text-ink">Please verify your email address before continuing.</p>
          <p className="mt-2 text-sm text-ink-muted">
            Creating a company requires a verified email — check <strong>{auth.user.email}</strong> for the
            verification link we sent when you registered.
          </p>
          <Button asChild variant="secondary" className="mt-3">
            <Link href="/dashboard">Back to Dashboard</Link>
          </Button>
        </div>
      </main>
    );
  }

  function set<K extends keyof CompanyCreateRequest>(key: K, value: CompanyCreateRequest[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!auth.accessToken) return;
    setSubmitting(true);
    setError(null);

    const payload: CompanyCreateRequest = {
      ...form,
      year_established: form.year_established || undefined,
      description: form.description || undefined,
      industry: form.industry || undefined,
      website: form.website || undefined,
      email: form.email || undefined,
      phone: form.phone || undefined,
      gst_number: form.gst_number || undefined,
      country: form.country || undefined,
      state: form.state || undefined,
      city: form.city || undefined,
    };

    const result = await createCompany(payload, auth.accessToken);
    setSubmitting(false);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    router.push(`/companies/${result.data.id}`);
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <h1 className="font-display text-xl font-semibold text-ink">Create a company</h1>
      {/* ForgeX Product Audit P1 #10: same reasoning as the Companies list
          empty state — this explains what filling out the form below
          actually gets you, instead of dropping straight into a form
          with no stated purpose. */}
      <p className="mt-1 text-sm text-ink-muted">
        Buyers discover you through ForgeX Consult. Verification comes next — it&apos;s what turns these details
        into evidence buyers can trust.
      </p>
      <form onSubmit={handleSubmit} className="mt-6 flex max-w-[520px] flex-col gap-4">
        <Input
          label="Company name *"
          id="name"
          required
          value={form.name}
          onChange={(e) => set("name", e.target.value)}
        />

        <div className="flex flex-col gap-1.5">
          <Input
            label="Legal name *"
            id="legal_name"
            required
            value={form.legal_name}
            onChange={(e) => set("legal_name", e.target.value)}
          />
          <span className="text-sm text-ink-muted">A URL-friendly slug is generated automatically from the company name.</span>
        </div>

        <Textarea
          label="Description"
          id="description"
          rows={3}
          value={form.description ?? ""}
          onChange={(e) => set("description", e.target.value)}
        />

        <Input
          label="Industry"
          id="industry"
          value={form.industry ?? ""}
          onChange={(e) => set("industry", e.target.value)}
          placeholder="e.g. Industrial Machinery"
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Website"
            id="website"
            type="url"
            value={form.website ?? ""}
            onChange={(e) => set("website", e.target.value)}
          />
          <Input
            label="Contact email"
            id="email"
            type="email"
            value={form.email ?? ""}
            onChange={(e) => set("email", e.target.value)}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Input
            label="Phone"
            id="phone"
            value={form.phone ?? ""}
            onChange={(e) => set("phone", e.target.value)}
          />
          <Input
            label="Year established"
            id="year_established"
            type="number"
            min={1800}
            max={2100}
            value={form.year_established ?? ""}
            onChange={(e) => set("year_established", e.target.value ? Number(e.target.value) : undefined)}
          />
        </div>

        <Select
          label="Company size"
          id="company_size"
          value={form.company_size ?? ""}
          onChange={(e) => set("company_size", (e.target.value || undefined) as CompanySize | undefined)}
        >
          <option value="">Select…</option>
          {COMPANY_SIZES.map((s) => (
            <option key={s} value={s}>
              {s} employees
            </option>
          ))}
        </Select>

        <Input
          label="GST number (optional)"
          id="gst_number"
          className="font-mono"
          value={form.gst_number ?? ""}
          onChange={(e) => set("gst_number", e.target.value)}
        />

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Input
            label="Country"
            id="country"
            value={form.country ?? ""}
            onChange={(e) => set("country", e.target.value)}
          />
          <Input
            label="State"
            id="state"
            value={form.state ?? ""}
            onChange={(e) => set("state", e.target.value)}
          />
          <Input
            label="City"
            id="city"
            value={form.city ?? ""}
            onChange={(e) => set("city", e.target.value)}
          />
        </div>

        {error && <p className="text-sm text-danger">{error}</p>}

        <Button type="submit" disabled={submitting} className="self-start">
          {submitting ? "Creating…" : "Create company"}
        </Button>
      </form>
    </main>
  );
}
