import { env } from "@/config/env";

export default function HomePage() {
  return (
    <main style={{ fontFamily: "ui-sans-serif, system-ui, sans-serif", padding: "3rem" }}>
      <h1>{env.appName}</h1>
      <p>Module 2 (authentication) is live. No other business features are implemented yet.</p>
      <ul>
        <li>
          Check API connectivity at <a href="/health">/health</a>.
        </li>
        <li>
          <a href="/register">Create an account</a> or <a href="/login">log in</a>.
        </li>
        <li>
          <a href="/dashboard">/dashboard</a> is a protected placeholder page.
        </li>
      </ul>
    </main>
  );
}
