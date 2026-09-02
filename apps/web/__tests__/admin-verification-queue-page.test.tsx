import type { PendingVerificationDocumentPage, PendingVerificationDocumentPublic } from "@platform/shared-types";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminVerificationQueuePage from "@/app/(app)/admin/verification/page";

/**
 * Phase 2B-2: the platform-admin verification queue page. Follows
 * use-require-platform-admin.test.tsx's hoisted-mock style for
 * @/contexts/AuthContext (need different auth states per test) and
 * companies-search page's Previous/Page X of Y/Next pagination
 * convention, which this page mirrors.
 */

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const authState = vi.hoisted(() => ({
  status: "authenticated" as "authenticated" | "unauthenticated" | "loading",
  accessToken: "token-abc" as string | null,
  user: { id: "u1", role: "admin" } as null | Record<string, unknown>,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => authState,
}));

const listPendingDocumentsMock = vi.hoisted(() => vi.fn());
vi.mock("@/lib/admin-verification", () => ({
  listPendingDocuments: listPendingDocumentsMock,
}));

function makeDoc(overrides: Partial<PendingVerificationDocumentPublic> = {}): PendingVerificationDocumentPublic {
  return {
    id: "doc-1",
    document_type: "gst_certificate",
    file_type: "pdf",
    file_url: "https://example.com/doc.pdf",
    status: "pending",
    uploaded_at: "2026-01-10T00:00:00Z",
    verified_at: null,
    review_note: null,
    expiry_date: null,
    version: 1,
    is_expired: false,
    company_id: "company-1",
    company_name: "Acme Manufacturing",
    ...overrides,
  };
}

function makePage(
  items: PendingVerificationDocumentPublic[],
  overrides: Partial<PendingVerificationDocumentPage> = {}
): PendingVerificationDocumentPage {
  return {
    items,
    total: items.length,
    page: 1,
    page_size: 20,
    total_pages: 1,
    ...overrides,
  };
}

function okResult(data: PendingVerificationDocumentPage) {
  return { success: true as const, data, meta: { requestId: "x", timestamp: "now" } };
}

function errResult(message: string) {
  return {
    success: false as const,
    error: { code: "QUEUE_FETCH_FAILED", message },
    meta: { requestId: "x", timestamp: "now" },
  };
}

describe("AdminVerificationQueuePage", () => {
  afterEach(() => {
    pushMock.mockClear();
    listPendingDocumentsMock.mockReset();
    authState.status = "authenticated";
    authState.accessToken = "token-abc";
    authState.user = { id: "u1", role: "admin" };
  });

  it("renders the queue for a platform admin", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc()])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("Verification Queue")).toBeTruthy());
    expect(screen.getByText("Acme Manufacturing")).toBeTruthy();
  });

  it("queries page=1, page_size=20, status=pending by default", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc()])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(listPendingDocumentsMock).toHaveBeenCalled());
    expect(listPendingDocumentsMock).toHaveBeenCalledWith("token-abc", {
      page: 1,
      pageSize: 20,
      status: "pending",
    });
  });

  it("renders the company name", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc({ company_name: "Bharat Steel Co" })])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("Bharat Steel Co")).toBeTruthy());
  });

  it("renders the document type", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc({ document_type: "iso" })])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("ISO Certificate")).toBeTruthy());
  });

  it("renders a PENDING badge", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc()])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("PENDING")).toBeTruthy());
  });

  it("renders the uploaded date", async () => {
    const uploadedAt = "2026-01-10T00:00:00Z";
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc({ uploaded_at: uploadedAt })])));

    render(<AdminVerificationQueuePage />);

    const expected = new Date(uploadedAt).toLocaleDateString();
    await waitFor(() => expect(screen.getByText(new RegExp(`Uploaded ${expected}`))).toBeTruthy());
  });

  it("renders the expiry date when present", async () => {
    listPendingDocumentsMock.mockResolvedValue(
      okResult(makePage([makeDoc({ expiry_date: "2027-06-01T00:00:00Z" })]))
    );

    render(<AdminVerificationQueuePage />);

    const expected = new Date("2027-06-01T00:00:00Z").toLocaleDateString();
    await waitFor(() => expect(screen.getByText(new RegExp(`Expires ${expected}`))).toBeTruthy());
  });

  it("does not render an expiry date when absent", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc({ expiry_date: null })])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("Acme Manufacturing")).toBeTruthy());
    expect(screen.queryByText(/Expires/)).toBeNull();
  });

  it("shows the empty state when nothing is pending", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("No documents awaiting review")).toBeTruthy());
  });

  it("shows the shared PageLoading state while the queue is loading", () => {
    listPendingDocumentsMock.mockReturnValue(new Promise(() => {}));

    render(<AdminVerificationQueuePage />);

    expect(screen.getByRole("status", { name: "Loading" })).toBeTruthy();
  });

  it("shows an inline error with Retry when the fetch fails", async () => {
    listPendingDocumentsMock.mockResolvedValue(errResult("Unable to load the verification queue."));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByText("Unable to load the verification queue.")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("Retry actually refetches the queue", async () => {
    listPendingDocumentsMock
      .mockResolvedValueOnce(errResult("Unable to load the verification queue."))
      .mockResolvedValueOnce(okResult(makePage([makeDoc()])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.getByText("Acme Manufacturing")).toBeTruthy());
    expect(listPendingDocumentsMock).toHaveBeenCalledTimes(2);
  });

  it("Next fetches the next page", async () => {
    listPendingDocumentsMock
      .mockResolvedValueOnce(okResult(makePage([makeDoc({ id: "doc-1" })], { page: 1, total_pages: 2, total: 2 })))
      .mockResolvedValueOnce(
        okResult(makePage([makeDoc({ id: "doc-2", company_name: "Page Two Co" })], { page: 2, total_pages: 2, total: 2 }))
      );

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => expect(screen.getByText("Page Two Co")).toBeTruthy());
    expect(listPendingDocumentsMock).toHaveBeenLastCalledWith("token-abc", {
      page: 2,
      pageSize: 20,
      status: "pending",
    });
  });

  it("Previous fetches the prior page", async () => {
    listPendingDocumentsMock
      .mockResolvedValueOnce(okResult(makePage([makeDoc({ id: "doc-1" })], { page: 1, total_pages: 2, total: 2 })))
      .mockResolvedValueOnce(
        okResult(makePage([makeDoc({ id: "doc-2", company_name: "Page Two Co" })], { page: 2, total_pages: 2, total: 2 }))
      )
      .mockResolvedValueOnce(
        okResult(makePage([makeDoc({ id: "doc-1", company_name: "Acme Manufacturing" })], { page: 1, total_pages: 2, total: 2 }))
      );

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(screen.getByText("Page Two Co")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));

    await waitFor(() => expect(screen.getByText("Acme Manufacturing")).toBeTruthy());
    expect(listPendingDocumentsMock).toHaveBeenLastCalledWith("token-abc", {
      page: 1,
      pageSize: 20,
      status: "pending",
    });
  });

  it("disables Previous on the first page", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc()], { page: 1, total_pages: 2, total: 2 })));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Previous" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "Previous" }).hasAttribute("disabled")).toBe(true);
  });

  it("disables Next on the last page", async () => {
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc()], { page: 1, total_pages: 1, total: 1 })));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Next" })).toBeTruthy());
    expect(screen.getByRole("button", { name: "Next" }).hasAttribute("disabled")).toBe(true);
  });

  it("the Review CTA navigates to a deterministic document route", async () => {
    listPendingDocumentsMock.mockResolvedValue(
      okResult(makePage([makeDoc({ id: "doc-42", company_id: "company-99" })]))
    );

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(screen.getByRole("link", { name: "Review" })).toBeTruthy());
    expect(screen.getByRole("link", { name: "Review" }).getAttribute("href")).toBe(
      "/admin/verification/doc-42?companyId=company-99"
    );
  });

  it("rejects a non-admin — no queue rendered, redirected to /dashboard, no fetch made", async () => {
    authState.user = { id: "u2", role: "viewer" };
    listPendingDocumentsMock.mockResolvedValue(okResult(makePage([makeDoc()])));

    render(<AdminVerificationQueuePage />);

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/dashboard"));
    expect(screen.queryByText("Verification Queue")).toBeNull();
    expect(listPendingDocumentsMock).not.toHaveBeenCalled();
  });
});
