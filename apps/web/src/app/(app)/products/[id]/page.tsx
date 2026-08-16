"use client";

import type { Offering, ProductDetail } from "@platform/shared-types";
import { Building2, Package } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useRequireAuth } from "@/hooks/useRequireAuth";
import { getProduct, getProductOfferings } from "@/lib/products";

/**
 * "Product Details" — Phase 4B minimal admin/testing page. Shows the
 * canonical Product (category, real dynamic specification values) and
 * every real Offering against it — the direct, visible proof of this
 * module's ABSOLUTE RULE: one Product, displayed once, with N real
 * companies listed below it, never duplicated.
 */
export default function ProductDetailPage() {
  const auth = useRequireAuth("/products");
  const params = useParams<{ id: string }>();
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [offerings, setOfferings] = useState<Offering[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    getProduct(params.id).then((result) => {
      if (result.success) setProduct(result.data);
      else setError(result.error.message);
    });
    getProductOfferings(params.id).then((result) => {
      if (result.success) setOfferings(result.data.items);
    });
  }, [auth.status, params.id]);

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;
  if (error) return <main className="p-8 text-sm text-danger">{error}</main>;
  if (product === null) return <main className="p-8 text-sm text-ink-muted">Loading…</main>;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <Link href="/products" className="text-sm text-ink-muted hover:text-ink">
        ← All products
      </Link>

      <div className="mt-4 flex items-start gap-4">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-accent-subtle text-accent">
          <Package size={26} aria-hidden />
        </div>
        <div>
          <h1 className="font-display text-2xl font-semibold text-ink">{product.name}</h1>
          <p className="mt-1 text-sm text-ink-muted">
            {product.category.name}
            {product.industry ? ` · ${product.industry}` : ""}
          </p>
          <span className="mt-2 inline-block rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-muted">
            {product.status}
          </span>
        </div>
      </div>

      {product.description && <p className="mt-4 text-sm text-ink">{product.description}</p>}

      {product.attributes.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-ink">Specifications</h2>
          <div className="mt-2 rounded-lg border border-border bg-canvas">
            {product.attributes.map((attr, i) => (
              <div
                key={attr.specification_id}
                className={`flex items-center justify-between px-4 py-2.5 text-sm ${i > 0 ? "border-t border-border" : ""}`}
              >
                <span className="text-ink-muted">{attr.specification_name}</span>
                <span className="font-medium text-ink">
                  {attr.value}
                  {attr.unit ? ` ${attr.unit}` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-ink">
          Offered by {offerings?.length ?? "…"} compan{offerings?.length === 1 ? "y" : "ies"}
        </h2>
        <p className="mt-1 text-xs text-ink-faint">
          One Product, many Companies — each row below is a real Offering, not a copy of this Product.
        </p>
        <div className="mt-2 flex flex-col gap-2">
          {offerings === null && (
            <div className="h-14 animate-pulse rounded-lg border border-border bg-surface" />
          )}
          {offerings?.map((offering) => (
            <Link
              key={offering.id}
              href={`/products/${product.id}/offerings/${offering.id}`}
              className="flex items-center gap-3 rounded-lg border border-border bg-canvas p-3.5 transition-colors hover:border-accent"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-accent-subtle text-accent">
                <Building2 size={16} aria-hidden />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{offering.company.name}</p>
                <p className="truncate text-xs text-ink-muted">
                  {offering.role} {offering.country ? `· ${offering.country}` : ""}
                </p>
              </div>
            </Link>
          ))}
          {offerings !== null && offerings.length === 0 && (
            <p className="text-sm text-ink-muted">No companies offer this product yet.</p>
          )}
        </div>
      </div>
    </main>
  );
}
