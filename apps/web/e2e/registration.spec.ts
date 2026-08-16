import { expect, test } from "@playwright/test";
import { Client } from "pg";

/**
 * End-to-end registration test — covers the complete real chain this
 * was written to verify: Browser -> Next.js frontend -> BFF route
 * (/api/auth/register) -> server-auth-client.ts -> FastAPI -> Pydantic
 * -> service layer -> Postgres -> response back to the browser ->
 * client-side redirect. A real browser (Playwright/Chromium), a real
 * running Next.js server, a real running FastAPI server, and a real
 * Postgres database — nothing here is mocked.
 *
 * Requires the full stack already running (see apps/web/e2e/README.md):
 *   - FastAPI on E2E_API_BASE_URL (default http://localhost:8000)
 *   - Next.js on E2E_BASE_URL (default http://localhost:3000)
 *   - Postgres reachable at E2E_DATABASE_URL
 */
const DATABASE_URL =
  process.env.E2E_DATABASE_URL ??
  "postgresql://platform_user:change_me_locally@localhost:5432/industrial_platform";

test.describe("registration — full stack", () => {
  test("register -> real DB row -> real session -> redirect to dashboard", async ({ page }) => {
    const uniqueEmail = `e2e-register-${Date.now()}@example.com`;
    const fullName = "E2E Registration Test";
    const password = "CorrectHorse9";

    // 1. Browser -> frontend: load the real registration page.
    await page.goto("/register");
    await expect(page.getByRole("heading", { name: "Create an account" })).toBeVisible();

    // 2. Browser -> frontend -> BFF -> FastAPI -> Pydantic -> service
    //    layer -> Postgres: submit the form and capture the BFF's real
    //    response to the browser (not mocked/intercepted).
    const responsePromise = page.waitForResponse(
      (res) => res.url().includes("/api/auth/register") && res.request().method() === "POST"
    );
    await page.getByLabel("Full name").fill(fullName);
    await page.getByLabel("Email").fill(uniqueEmail);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: "Create account" }).click();

    const response = await responsePromise;
    expect(response.status(), "BFF should return 201 for a successful registration").toBe(201);
    const body = await response.json();
    expect(body.success).toBe(true);
    expect(body.data.user.email).toBe(uniqueEmail);
    expect(typeof body.data.access_token).toBe("string");

    // 3. Database: the row this request created must actually exist —
    //    verified with a direct query, not inferred from the API
    //    response alone.
    const client = new Client({ connectionString: DATABASE_URL });
    await client.connect();
    try {
      const result = await client.query(
        "SELECT id, email, full_name, hashed_password, is_email_verified FROM users WHERE email = $1",
        [uniqueEmail]
      );
      expect(result.rows).toHaveLength(1);
      expect(result.rows[0].full_name).toBe(fullName);
      // The password must be hashed, never stored/returned in plain text.
      expect(result.rows[0].hashed_password).not.toBe(password);
      expect(result.rows[0].hashed_password.length).toBeGreaterThan(20);
      expect(result.rows[0].is_email_verified).toBe(false);
    } finally {
      await client.end();
    }

    // 4. Browser: redirect to the authenticated dashboard must actually
    //    happen, and it must show this exact user's real data — proof
    //    the session round-tripped correctly, not just that an API call
    //    returned 201.
    await page.waitForURL("**/dashboard", { timeout: 15_000 });
    // Multiple elements legitimately show the name (the shell's profile
    // menu, twice, plus the dashboard page's own content) — .first() is
    // enough to confirm the redirect landed with the correct user's data.
    await expect(page.getByText(fullName).first()).toBeVisible();
  });

  test("duplicate email registration is rejected with 409, not silently accepted", async ({ page }) => {
    const email = `e2e-duplicate-${Date.now()}@example.com`;
    const password = "CorrectHorse9";

    async function attemptRegister(name: string) {
      await page.goto("/register");
      const responsePromise = page.waitForResponse(
        (res) => res.url().includes("/api/auth/register") && res.request().method() === "POST"
      );
      await page.getByLabel("Full name").fill(name);
      await page.getByLabel("Email").fill(email);
      await page.getByLabel("Password").fill(password);
      await page.getByRole("button", { name: "Create account" }).click();
      return responsePromise;
    }

    const first = await attemptRegister("First User");
    expect(first.status()).toBe(201);

    const second = await attemptRegister("Second User");
    expect(second.status(), "the real upstream status must be preserved, not collapsed to 422").toBe(
      409
    );
    const secondBody = await second.json();
    expect(secondBody.error.code).toBe("EMAIL_ALREADY_REGISTERED");
  });
});
