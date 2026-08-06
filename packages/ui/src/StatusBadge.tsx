import type { DependencyStatus } from "@platform/shared-types";

export interface StatusBadgeProps {
  status: DependencyStatus;
  label: string;
}

const COLORS: Record<DependencyStatus, string> = {
  ok: "#1a7f37",
  degraded: "#9a6700",
  down: "#cf222e",
};

/** Minimal, dependency-light status indicator used on health/diagnostics screens. */
export function StatusBadge({ status, label }: StatusBadgeProps) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.4rem",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        fontSize: "0.85rem",
      }}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          backgroundColor: COLORS[status],
          display: "inline-block",
        }}
      />
      {label}
    </span>
  );
}
