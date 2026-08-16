"use client";

import type { Offering } from "@platform/shared-types";
import { Building2, CheckCircle2, HelpCircle } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getOffering } from "@/lib/products";

const ROLE_LABELS: Record<string, string> = {
  manufacturer: "Manufacturer",
  supplier: "Supplier",
  distributor: "Distributor",
  exporter: "Exporter",
  service_provider: "Service Provider",
};

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2.5 last:border-b-0">
      <span className="text-sm text-ink-muted">{label}</span>
      <span className="text-sm font-medium text-ink">{value ?? "Not specified"}</span>
    </div>
  );
}

/**
 * "Offering Details" — Phase 4B minimal admin/testing page. Everything
 * shown here is company-specific — MOQ, lead time, capacity, country,
 * offering-level verification status — never the Product's own data
 * (see app.models.offering's docstring: this is deliberately the only
 * place these fields live).
 */
export default function OfferingDetailPage() {
  const auth = useRequireAuth("/products");
  const params = useParams<{ id: string; offeringId: string }>();
  const [offering, setOffering] = useState<Offering | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    getOffering(params.id, params.offeringId).then((result) => {
      if (result.success) setOffering(result.data);
      else setError(result.error.message);
    });
  }, [auth.status, params.id, params.offeringId]);

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;
  if (error) return <main className="p-8 text-sm text-danger">{error}</main>;
  if (offering === null) return <main className="p-8 text-sm text-ink-muted">Loading…</main>;

  return (
    <main className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <Link href={`/products/${params.id}`} className="text-sm text-ink-muted hover:text-ink">
        ← {offering.product.name}
      </Link>

      <div className="mt-4 flex items-start gap-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
          <Building2 size={26} aria-hidden />
        </div>
        <div>
          <h1 className="font-display text-xl font-semibold text-ink">{offering.company.name}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {ROLE_LABELS[offering.role]} of {offering.product.name}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 text-sm">
        {offering.verification_status === "verified" ? (
          <CheckCircle2 size={14} className="text-success" aria-hidden />
        ) : (
          <HelpCircle size={14} className="text-ink-faint" aria-hidden />
        )}
        <span className={offering.verification_status === "verified" ? "text-success" : "text-ink-muted"}>
          {offering.verification_status === "verified" ? "Offering verified" : "Offering not yet verified"}
        </span>
      </div>

      <div className="mt-6 rounded-lg border border-border bg-canvas px-4">
        <Row label="Role" value={ROLE_LABELS[offering.role] ?? offering.role} />
        <Row label="MOQ" value={offering.moq} />
        <Row label="Lead time" value={offering.lead_time} />
        <Row label="Capacity" value={offering.capacity} />
        <Row label="Country" value={offering.country} />
        <Row label="Status" value={offering.status} />
      </div>

      <p className="mt-4 text-xs text-ink-faint">
        This data belongs to {offering.company.name}&apos;s offering — not to the Product itself. Other
        companies offering the same product have their own, independent MOQ, lead time, and terms.
      </p>
    </main>
  );
}
