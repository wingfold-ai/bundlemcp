import { chromium, type FullConfig } from "@playwright/test";

// Sign in once through the real OIDC flow (gateway -> Keycloak -> back) and
// persist the session for every test (UI-2 exercised by login.spec.ts too).
export default async function globalSetup(config: FullConfig) {
  const webUrl = process.env.WEB_URL ?? "http://localhost:3000";
  const browser = await chromium.launch();
  const page = await browser.newPage();

  await page.goto(webUrl);
  // middleware redirects to the gateway /login, which redirects to Keycloak
  // (hostname `keycloak` — see TESTING.md /etc/hosts prerequisite)
  await page.waitForURL(/(localhost|keycloak):8080/, { timeout: 30_000 });
  await page.locator("#username").fill("admin");
  await page.locator("#password").fill("admin");
  await page.locator("#kc-login").click();
  // back on the web app, signed in
  await page.waitForURL(new RegExp(webUrl.replace(/[/:]/g, "\\$&")), {
    timeout: 30_000,
  });
  await page.waitForSelector('[data-testid="app-title"]');

  await page.context().storageState({ path: "tests/.auth/admin.json" });
  await browser.close();
}
