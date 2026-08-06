/**
 * Central, typed accessor for web-app environment variables.
 * Import this instead of reading process.env directly anywhere else,
 * so a missing/invalid var fails fast at startup with a clear message.
 */
function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(`Missing required environment variable: ${name}`);
  }
  return value;
}

export const env = {
  appName: process.env.NEXT_PUBLIC_APP_NAME ?? "Industrial Intelligence Platform",
  apiBaseUrl: required(
    "NEXT_PUBLIC_API_BASE_URL",
    process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"
  ),
  nodeEnv: process.env.NODE_ENV ?? "development",
};
