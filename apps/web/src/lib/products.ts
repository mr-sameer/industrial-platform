/**
 * Industrial Product Graph API client functions — Phase 4B. Mirrors
 * lib/companies.ts's conventions exactly: direct calls to FastAPI, no
 * BFF (same reasoning as that file's own docstring — plain Bearer
 * auth, no cookie/CSRF surface to protect).
 */
import type {
  ApiResponse,
  Offering,
  OfferingPage,
  ProductCategory,
  ProductCreateRequest,
  ProductDetail,
  ProductSearchPage,
  ProductSpecification,
} from "@platform/shared-types";

import { apiFetch } from "@/lib/api-client";

function authHeaders(accessToken: string): HeadersInit {
  return { Authorization: `Bearer ${accessToken}` };
}

export function listCategories() {
  return apiFetch<ProductCategory[]>("/api/v1/product-categories");
}

export function listCategorySpecifications(categoryId: string) {
  return apiFetch<ProductSpecification[]>(`/api/v1/product-categories/${categoryId}/specifications`);
}

export function searchProducts(params: {
  name?: string;
  category_id?: string;
  industry?: string;
  page?: number;
  page_size?: number;
}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) query.set(key, String(value));
  }
  return apiFetch<ProductSearchPage>(`/api/v1/products/search?${query.toString()}`);
}

export function getProduct(productId: string) {
  return apiFetch<ProductDetail>(`/api/v1/products/${productId}`);
}

export function getProductBySlug(slug: string) {
  return apiFetch<ProductDetail>(`/api/v1/products/slug/${slug}`);
}

export function getProductOfferings(productId: string, page = 1, pageSize = 20) {
  return apiFetch<OfferingPage>(
    `/api/v1/products/${productId}/offerings?page=${page}&page_size=${pageSize}`
  );
}

export function createProduct(payload: ProductCreateRequest, accessToken: string) {
  return apiFetch<ProductDetail>("/api/v1/products", {
    method: "POST",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  });
}

export async function getOffering(
  productId: string,
  offeringId: string
): Promise<ApiResponse<Offering>> {
  // No standalone GET /offerings/{id} endpoint exists (Phase 4B scoped
  // reads to GET /products/{id}/offerings) — resolved client-side by
  // fetching the product's offering list and finding the match. See
  // this module's completion report for why a dedicated endpoint
  // wasn't added: the offering detail page is minimal/internal, and
  // this avoids an extra API surface for a single-page convenience.
  const page = await getProductOfferings(productId, 1, 100);
  if (!page.success) return page;
  const offering = page.data.items.find((o) => o.id === offeringId);
  if (!offering) {
    return {
      success: false,
      error: { code: "OFFERING_NOT_FOUND", message: "No offering with that ID exists for this product." },
      meta: { requestId: "client-side", timestamp: new Date().toISOString() },
    };
  }
  return { success: true, data: offering, meta: page.meta };
}
