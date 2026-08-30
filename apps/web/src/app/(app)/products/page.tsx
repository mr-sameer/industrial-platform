"use client";

import type { ProductSearchResult } from "@platform/shared-types";
import { Package } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { searchProducts } from "@/lib/products";

/**
 * "Products List" — Phase 4B minimal admin/testing page, per this
 * module's explicit scope ("Only implement minimal admin/testing
 * pages... DO NOT redesign homepage/consult/discovery"). Not a
 * polished public page — an internal view onto the real Product Graph
 * data via GET /products/search, for verifying and browsing what's
 * actually in the system.
 *
 * ForgeX Product Audit P1 #5: that "not a polished public page" intent
 * previously lived only in this comment — the rendered page gave a
 * visitor zero signal it wasn't a finished feature. The "Internal"
 * badge below (and its siblings on the two detail pages one level in)
 * makes that honest instead of assumed.
 */
export default function ProductsListPage() {
  const auth = useRequireAuth("/products");
  const [products, setProducts] = useState<ProductSearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    searchProducts({ page: 1, page_size: 50 }).then((result) => {
      if (result.success) setProducts(result.data.items);
      else setError(result.error.message);
    });
  }, [auth.status]);

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="font-display text-xl font-semibold text-ink">Products</h1>
            <Badge variant="warning">Internal</Badge>
          </div>
          <p className="mt-1 text-sm text-ink-muted">
            An internal view of what&apos;s in the Product Graph, for verifying and browsing the
            data — not a customer-facing catalog.
          </p>
        </div>
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      {products === null && !error && (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-16 animate-pulse rounded-lg border border-border bg-surface" />
          ))}
        </div>
      )}

      {products !== null && products.length === 0 && (
        <p className="text-sm text-ink-muted">No published products yet.</p>
      )}

      {products !== null && products.length > 0 && (
        <div className="flex flex-col gap-2">
          {products.map((product) => (
            <Link
              key={product.id}
              href={`/products/${product.id}`}
              className="flex items-center gap-3 rounded-lg border border-border bg-canvas p-4 transition-colors hover:border-accent"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-accent-subtle text-accent">
                <Package size={18} aria-hidden />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-ink">{product.name}</p>
                <p className="truncate text-xs text-ink-muted">{product.industry ?? "Industry not set"}</p>
              </div>
              <span className="shrink-0 rounded-full bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-muted">
                {product.offering_count} offering{product.offering_count === 1 ? "" : "s"}
              </span>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
