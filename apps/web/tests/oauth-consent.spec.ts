import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { createHash, randomBytes } from "node:crypto";
import { test, expect, given, when, then } from "./gherkin";
import { STORAGE, GATEWAY_URL } from "./flows";
import { testTitle } from "./spec-map";

test.use({ storageState: STORAGE });

// The consent page's CSP restricts form-action, and Chromium applies that to the
// redirect answering the Approve/Deny post. HTTP clients ignore CSP, so only a
// real browser proves the client's redirect URI is reached. The client lives on
// 127.0.0.1, another origin than the gateway on localhost.
const SERVICE_KEY =
  process.env.BUNDLEMCP_INITIAL_SERVICE_KEY ?? "bmcp_sk_devservicekey000000000000000000000000";
const ENDPOINT = "oauthdemo";

let callback: Server;
let redirectUri: string;

test.beforeAll(async () => {
  callback = createServer((_req, res) => res.end("client callback"));
  await new Promise<void>((resolve) => callback.listen(0, "127.0.0.1", resolve));
  redirectUri = `http://127.0.0.1:${(callback.address() as AddressInfo).port}/callback`;
});

test.afterAll(() => new Promise<void>((resolve) => callback.close(() => resolve())));

function authorizeUrl(clientId: string, state: string): string {
  const challenge = createHash("sha256")
    .update(randomBytes(32).toString("base64url"))
    .digest("base64url");
  const params = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: "code",
    code_challenge: challenge,
    code_challenge_method: "S256",
    state,
    resource: `${GATEWAY_URL}/${ENDPOINT}/mcp`,
  });
  return `${GATEWAY_URL}/oauth/authorize?${params}`;
}

test(testTitle("E2E-17"), async ({ page, steps }) => {
  let clientId = "";
  let landed: URL;

  await steps.play([
    given("an OAuth endpoint and a client registered with a redirect URI on another origin", { req: "OAS-2" }, async () => {
      // Plain fetch, not the `request` fixture: that one carries the stored admin
      // cookie, and a cookie-authenticated write must pass the CSRF check.
      const endpoint = await fetch(`${GATEWAY_URL}/api/v1/endpoints/${ENDPOINT}`, {
        method: "PUT",
        headers: { Authorization: `Bearer ${SERVICE_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          name: ENDPOINT,
          bundle_name: "demo",
          profile: "claude",
          auth_modes: ["oauth"],
        }),
      });
      expect(endpoint.status, await endpoint.text()).toBe(200);
      const registered = await fetch(`${GATEWAY_URL}/oauth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ redirect_uris: [redirectUri], client_name: "E2E consent client" }),
      });
      expect(registered.status).toBe(201);
      clientId = (await registered.json()).client_id;
    }),
    when("the signed-in user denies the consent screen", { req: "OAS-11" }, async () => {
      await page.goto(authorizeUrl(clientId, "deny-state"));
      await page.getByRole("button", { name: "Deny" }).click();
      await page.waitForURL((url) => url.href.startsWith(redirectUri));
      landed = new URL(page.url());
    }),
    then("the client's redirect URI receives error=access_denied", { req: "SEC-6" }, async () => {
      expect(landed.searchParams.get("error")).toBe("access_denied");
      expect(landed.searchParams.get("state")).toBe("deny-state");
    }),
    when("the user approves the consent screen", { req: "OAS-11" }, async () => {
      await page.goto(authorizeUrl(clientId, "approve-state"));
      await page.getByRole("button", { name: "Approve" }).click();
      await page.waitForURL((url) => url.href.startsWith(redirectUri));
      landed = new URL(page.url());
    }),
    then("the client's redirect URI receives the code and state", { req: "SEC-6" }, async () => {
      expect(landed.searchParams.get("code")).toBeTruthy();
      expect(landed.searchParams.get("state")).toBe("approve-state");
    }),
  ]);
});
