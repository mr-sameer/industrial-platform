"use client";

import type { VerificationScorePublic } from "@platform/shared-types";
import { VERIFICATION_LEVEL_LABELS } from "@platform/shared-types";

import * as ui from "@/lib/ui-styles";

/**
 * Shared "Verification Progress" display — Module 3B. Used by the
 * Verification Dashboard page and embeddable anywhere else a compact
 * progress view is useful (kept as one component per
 * docs/standards/coding-standards.md's "no duplicated logic").
 */
export function VerificationProgress({ score }: { score: VerificationScorePublic }) {
  return (
    <div style={ui.card}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h3 style={{ margin: 0 }}>{VERIFICATION_LEVEL_LABELS[score.level]}</h3>
        <span style={{ fontSize: "1.5rem", fontWeight: 700 }}>{score.percentage}%</span>
      </div>
      <div
        style={{
          height: 8,
          borderRadius: 4,
          background: "#eee",
          marginTop: "0.75rem",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${score.percentage}%`,
            background: "#1a7f37",
            transition: "width 0.3s ease",
          }}
        />
      </div>

      {score.next_level && (
        <p style={ui.mutedText}>
          Next level: <strong>{VERIFICATION_LEVEL_LABELS[score.next_level]}</strong>
        </p>
      )}

      {score.missing_requirements.length > 0 && (
        <div style={{ marginTop: "1rem" }}>
          <h4 style={{ marginBottom: "0.5rem" }}>Missing requirements</h4>
          <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
            {score.missing_requirements.map((req) => (
              <li key={req.key} style={{ marginBottom: "0.25rem" }}>
                {req.label} <span style={ui.mutedText}>(+{req.weight}%)</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {score.missing_requirements.length === 0 && (
        <p style={{ color: "#1a7f37", marginTop: "1rem" }}>All requirements met — fully verified.</p>
      )}
    </div>
  );
}
