import type { HealthCheckResponse } from "@platform/shared-types";
import { StatusBadge } from "@platform/ui";

import { apiFetch } from "@/lib/api-client";

export const dynamic = "force-dynamic";

export default async function HealthPage() {
  const result = await apiFetch<HealthCheckResponse>("/health");

  return (
    <main style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif", padding: "3rem" }}>
      <h1>System Health</h1>
      <section style={{ marginTop: "1.5rem" }}>
        <h2>Web</h2>
        <StatusBadge status="ok" label="web service reachable" />
      </section>
      <section style={{ marginTop: "1.5rem" }}>
        <h2>API</h2>
        {result.success ? (
          <>
            <StatusBadge status={result.data.status} label={`api: ${result.data.status}`} />
            <ul>
              <li>
                <StatusBadge
                  status={result.data.dependencies.database.status}
                  label={`database: ${result.data.dependencies.database.status}`}
                />
              </li>
              <li>
                <StatusBadge
                  status={result.data.dependencies.redis.status}
                  label={`redis: ${result.data.dependencies.redis.status}`}
                />
              </li>
            </ul>
          </>
        ) : (
          <StatusBadge status="down" label={result.error.message} />
        )}
      </section>
    </main>
  );
}
