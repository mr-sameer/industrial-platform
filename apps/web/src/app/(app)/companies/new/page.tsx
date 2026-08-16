"use client";

import type { CompanyCreateRequest, CompanySize } from "@platform/shared-types";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { createCompany } from "@/lib/companies";
import * as ui from "@/lib/ui-styles";

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

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
  if (auth.status === "unauthenticated") return null;

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
    <main style={ui.page}>
      <h1>Create a company</h1>
      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem", maxWidth: 520 }}>
        <div style={ui.formField}>
          <label htmlFor="name">Company name *</label>
          <input
            id="name"
            required
            style={ui.input}
            value={form.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </div>

        <div style={ui.formField}>
          <label htmlFor="legal_name">Legal name *</label>
          <input
            id="legal_name"
            required
            style={ui.input}
            value={form.legal_name}
            onChange={(e) => set("legal_name", e.target.value)}
          />
          <span style={ui.mutedText}>A URL-friendly slug is generated automatically from the company name.</span>
        </div>

        <div style={ui.formField}>
          <label htmlFor="description">Description</label>
          <textarea
            id="description"
            rows={3}
            style={ui.input}
            value={form.description ?? ""}
            onChange={(e) => set("description", e.target.value)}
          />
        </div>

        <div style={ui.formField}>
          <label htmlFor="industry">Industry</label>
          <input
            id="industry"
            style={ui.input}
            value={form.industry ?? ""}
            onChange={(e) => set("industry", e.target.value)}
            placeholder="e.g. Industrial Machinery"
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div style={ui.formField}>
            <label htmlFor="website">Website</label>
            <input
              id="website"
              type="url"
              style={ui.input}
              value={form.website ?? ""}
              onChange={(e) => set("website", e.target.value)}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="email">Contact email</label>
            <input
              id="email"
              type="email"
              style={ui.input}
              value={form.email ?? ""}
              onChange={(e) => set("email", e.target.value)}
            />
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
          <div style={ui.formField}>
            <label htmlFor="phone">Phone</label>
            <input
              id="phone"
              style={ui.input}
              value={form.phone ?? ""}
              onChange={(e) => set("phone", e.target.value)}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="year_established">Year established</label>
            <input
              id="year_established"
              type="number"
              min={1800}
              max={2100}
              style={ui.input}
              value={form.year_established ?? ""}
              onChange={(e) => set("year_established", e.target.value ? Number(e.target.value) : undefined)}
            />
          </div>
        </div>

        <div style={ui.formField}>
          <label htmlFor="company_size">Company size</label>
          <select
            id="company_size"
            style={ui.input}
            value={form.company_size ?? ""}
            onChange={(e) => set("company_size", (e.target.value || undefined) as CompanySize | undefined)}
          >
            <option value="">Select…</option>
            {COMPANY_SIZES.map((s) => (
              <option key={s} value={s}>
                {s} employees
              </option>
            ))}
          </select>
        </div>

        <div style={ui.formField}>
          <label htmlFor="gst_number">GST number (optional)</label>
          <input
            id="gst_number"
            style={ui.input}
            value={form.gst_number ?? ""}
            onChange={(e) => set("gst_number", e.target.value)}
          />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
          <div style={ui.formField}>
            <label htmlFor="country">Country</label>
            <input
              id="country"
              style={ui.input}
              value={form.country ?? ""}
              onChange={(e) => set("country", e.target.value)}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="state">State</label>
            <input
              id="state"
              style={ui.input}
              value={form.state ?? ""}
              onChange={(e) => set("state", e.target.value)}
            />
          </div>
          <div style={ui.formField}>
            <label htmlFor="city">City</label>
            <input
              id="city"
              style={ui.input}
              value={form.city ?? ""}
              onChange={(e) => set("city", e.target.value)}
            />
          </div>
        </div>

        {error && <p style={ui.errorText}>{error}</p>}

        <button type="submit" disabled={submitting} style={ui.button}>
          {submitting ? "Creating…" : "Create company"}
        </button>
      </form>
    </main>
  );
}
