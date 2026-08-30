"use client";

import type { DocumentType, VerificationDocumentPublic } from "@platform/shared-types";
import { DOCUMENT_TYPE_LABELS } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { useRequireAuth } from "@/hooks/useRequireAuth";
import { deleteDocument, listDocuments, replaceDocument, uploadDocument } from "@/lib/company-verification";

const DOCUMENT_TYPES = Object.keys(DOCUMENT_TYPE_LABELS) as DocumentType[];

/** Documents — Module 3B. Upload/replace/delete verification evidence. */
export default function DocumentsPage() {
  const params = useParams<{ id: string }>();
  const auth = useRequireAuth(`/companies/${params.id}/documents`);
  const [documents, setDocuments] = useState<VerificationDocumentPublic[] | null>(null);
  const [documentType, setDocumentType] = useState<DocumentType>("gst_certificate");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replaceInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const fetchDocuments = useCallback(async () => {
    if (!auth.accessToken) return;
    const result = await listDocuments(params.id, auth.accessToken);
    if (result.success) {
      setDocuments(result.data);
    } else {
      setError(result.error.message);
    }
  }, [auth.accessToken, params.id]);

  useEffect(() => {
    if (auth.status === "authenticated") fetchDocuments();
  }, [auth.status, fetchDocuments]);

  if (auth.status === "loading") return <main className="p-8 text-sm text-ink-muted">Loading…</main>;
  if (auth.status === "unauthenticated") return null;

  async function handleUpload() {
    const file = fileInputRef.current?.files?.[0];
    if (!file || !auth.accessToken) return;
    setUploading(true);
    setError(null);
    const result = await uploadDocument(params.id, documentType, file, auth.accessToken);
    setUploading(false);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
    fetchDocuments();
  }

  async function handleReplace(documentId: string) {
    const file = replaceInputRefs.current[documentId]?.files?.[0];
    if (!file || !auth.accessToken) return;
    setError(null);
    const result = await replaceDocument(params.id, documentId, file, auth.accessToken);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    fetchDocuments();
  }

  async function handleDelete(documentId: string) {
    if (!auth.accessToken) return;
    const result = await deleteDocument(params.id, documentId, auth.accessToken);
    if (!result.success) {
      setError(result.error.message);
      return;
    }
    fetchDocuments();
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <p>
        <Link href={`/companies/${params.id}/verification`} className="text-sm text-accent hover:text-accent-hover">
          &larr; Back to verification
        </Link>
      </p>
      <h1 className="mt-2 font-display text-xl font-semibold text-ink">Documents</h1>

      <div className="mt-6 rounded-lg border border-border bg-canvas p-5">
        <h3 className="text-sm font-semibold text-ink">Upload a document</h3>
        <div className="mt-3 flex flex-wrap items-end gap-3">
          <Select
            label="Document type"
            className="w-56"
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value as DocumentType)}
          >
            {DOCUMENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {DOCUMENT_TYPE_LABELS[t]}
              </option>
            ))}
          </Select>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,image/jpeg,image/png,image/webp"
            className="text-sm text-ink-muted"
          />
          <Button type="button" disabled={uploading} onClick={handleUpload}>
            {uploading ? "Uploading…" : "Upload"}
          </Button>
        </div>
        <p className="mt-2 text-sm text-ink-muted">PDF or image, up to 15 MB.</p>
      </div>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      {documents === null && !error && <p className="mt-4 text-sm text-ink-muted">Loading documents…</p>}
      {documents !== null && documents.length === 0 && (
        <div className="mt-4 rounded-lg border border-border bg-canvas p-8 text-center">
          <p className="text-sm text-ink-muted">No documents uploaded yet.</p>
        </div>
      )}

      {documents !== null && documents.length > 0 && (
        <div className="mt-4 grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {documents.map((doc) => (
            <div key={doc.id} className="rounded-lg border border-border bg-canvas p-5">
              <h4 className="text-sm font-semibold text-ink">{DOCUMENT_TYPE_LABELS[doc.document_type]}</h4>
              <p className="mt-1 text-sm text-ink-muted">
                Status: {doc.status} · v{doc.version}
                {doc.is_expired && " · expired"}
              </p>
              <p className="mt-1">
                <a href={doc.file_url} target="_blank" rel="noreferrer" className="text-sm text-accent hover:text-accent-hover">
                  View file
                </a>
              </p>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <input
                  ref={(el) => {
                    replaceInputRefs.current[doc.id] = el;
                  }}
                  type="file"
                  accept="application/pdf,image/jpeg,image/png,image/webp"
                  className="max-w-[140px] text-xs text-ink-muted"
                />
                <Button type="button" variant="secondary" size="sm" onClick={() => handleReplace(doc.id)}>
                  Replace
                </Button>
                <Button type="button" variant="danger" size="sm" onClick={() => handleDelete(doc.id)}>
                  Delete
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
