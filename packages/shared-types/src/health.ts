export type DependencyStatus = "ok" | "degraded" | "down";

export interface DependencyHealth {
  status: DependencyStatus;
  latencyMs?: number;
  message?: string;
}

export interface HealthCheckResponse {
  status: DependencyStatus;
  service: string;
  version: string;
  uptimeSeconds: number;
  dependencies: {
    database: DependencyHealth;
    redis: DependencyHealth;
  };
}
