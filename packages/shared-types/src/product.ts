/**
 * Industrial Product Graph types — Phase 4B. Mirrors
 * apps/api/app/schemas/product.py field-for-field.
 */

export type ProductStatus = "draft" | "published" | "archived";
export type SpecificationDataType = "number" | "text" | "enum" | "boolean" | "range";
export type OfferingRole = "manufacturer" | "supplier" | "distributor" | "exporter" | "service_provider";
export type OfferingVerificationStatus = "unverified" | "verified";
export type OfferingStatus = "active" | "inactive";

export interface ProductCategory {
  id: string;
  name: string;
  slug: string;
  parent_id: string | null;
}

export interface ProductSpecification {
  id: string;
  category_id: string;
  name: string;
  unit: string | null;
  datatype: SpecificationDataType;
  enum_options: string[] | null;
  required: boolean;
}

export interface ProductAttribute {
  specification_id: string;
  specification_name: string;
  unit: string | null;
  value: string;
}

export interface ProductAttributeInput {
  specification_id: string;
  value: string;
}

export interface ProductCreateRequest {
  name: string;
  description?: string;
  product_family?: string;
  category_id: string;
  industry?: string;
  attributes?: ProductAttributeInput[];
}

export interface ProductUpdateRequest {
  name?: string;
  description?: string;
  product_family?: string;
  industry?: string;
  status?: ProductStatus;
  attributes?: ProductAttributeInput[];
}

export interface ProductSearchResult {
  id: string;
  name: string;
  slug: string;
  product_family: string | null;
  category_id: string;
  industry: string | null;
  status: ProductStatus;
  offering_count: number;
}

export interface ProductDetail {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  product_family: string | null;
  category: ProductCategory;
  industry: string | null;
  status: ProductStatus;
  attributes: ProductAttribute[];
  created_at: string;
  updated_at: string;
}

export interface ProductSearchPage {
  items: ProductSearchResult[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OfferingCompanySummary {
  id: string;
  name: string;
  slug: string;
  verification_status: string;
}

export interface OfferingProductSummary {
  id: string;
  name: string;
  slug: string;
}

export interface Offering {
  id: string;
  company: OfferingCompanySummary;
  product: OfferingProductSummary;
  role: OfferingRole;
  moq: string | null;
  lead_time: string | null;
  capacity: string | null;
  country: string | null;
  verification_status: OfferingVerificationStatus;
  status: OfferingStatus;
  created_at: string;
  updated_at: string;
}

export interface OfferingPage {
  items: Offering[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
