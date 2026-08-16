"use client";

import type { DocumentType, VerificationDocumentPublic } from "@platform/shared-types";
import { DOCUMENT_TYPE_LABELS } from "@platform/shared-types";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";


import { useRequireAuth } from "@/hooks/useRequireAuth";
import { deleteDocument, listDocuments, replaceDocument, uploadDocument } from "@/lib/company-verification";
import * as ui from "@/lib/ui-styles";

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

  if (auth.status === "loading") return <main style={ui.page}>Loading…</main>;
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
    <main style={ui.page}>
      <p>
        <Link href={`/companies/${params.id}/verification`}>&larr; Back to verification</Link>
      </p>
      <h1>Documents</h1>

      <div style={{ ...ui.card, marginBottom: "1.5rem" }}>
        <h3 style={{ marginTop: 0 }}>Upload a document</h3>
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
          <select
            style={ui.input}
            value={documentType}
            onChange={(e) => setDocumentType(e.target.value as DocumentType)}
          >
            {DOCUMENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {DOCUMENT_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
          <input ref={fileInputRef} type="file" accept="application/pdf,image/jpeg,image/png,image/webp" />
          <button type="button" style={ui.button} disabled={uploading} onClick={handleUpload}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
        </div>
        <p style={ui.mutedText}>PDF or image, up to 15 MB.</p>
      </div>

      {error && <p style={ui.errorText}>{error}</p>}

      {documents === null && !error && <p style={ui.mutedText}>Loading documents…</p>}
      {documents !== null && documents.length === 0 && (
        <div style={{ ...ui.card, textAlign: "center", padding: "2rem" }}>
          <p>No documents uploaded yet.</p>
        </div>
      )}

      {documents !== null && documents.length > 0 && (
        <div style={ui.cardGrid}>
          {documents.map((doc) => (
            <div key={doc.id} style={ui.card}>
              <h4 style={{ margin: "0 0 0.35rem" }}>{DOCUMENT_TYPE_LABELS[doc.document_type]}</h4>
              <p style={ui.mutedText}>
                Status: {doc.status} · v{doc.version}
                {doc.is_expired && " · expired"}
              </p>
              <p>
                <a href={doc.file_url} target="_blank" rel="noreferrer">
                  View file
                </a>
              </p>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                <input
                  ref={(el) => {
                    replaceInputRefs.current[doc.id] = el;
                  }}
                  type="file"
                  accept="application/pdf,image/jpeg,image/png,image/webp"
                  style={{ maxWidth: 140 }}
                />
                <button type="button" style={ui.buttonSecondary} onClick={() => handleReplace(doc.id)}>
                  Replace
                </button>
                <button type="button" style={ui.buttonDanger} onClick={() => handleDelete(doc.id)}>
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
