import { type Page } from "@playwright/test";
import { scenario, scenarioRequirements } from "./spec-map";

// Video-overlay primitives for the recorded e2e run (PW_VIDEO=1). Everything
// here is a hard no-op when not recording, and every overlay is
// pointer-events:none so it can never swallow a click or change what the tests
// actually exercise.

export const RECORDING = process.env.PW_VIDEO === "1";

// Text can contain literals like `https://<host>/…`; the overlays are built
// with innerHTML, so escape before injecting or the browser eats them.
export function esc(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// One line of the intro card's scenario outline (a step without its body).
export interface PlanLine {
  keyword: string;
  text: string;
  req?: string;
}

const KEYWORD_COLOR: Record<string, string> = {
  Given: "#1f6feb",
  When: "#d29922",
  Then: "#3fb950",
  And: "#6e7681",
};

// Paints the caption bar. Runs in the browser, so it must stay self-contained:
// it is used both for the current page and (via addInitScript) for every page
// loaded afterwards, which is what keeps the caption alive across navigations.
function paintCaption(html: string): void {
  const draw = () => {
    let el = document.getElementById("__e2e_caption__");
    if (!el) {
      el = document.createElement("div");
      el.id = "__e2e_caption__";
      el.style.cssText = [
        "position:fixed;left:0;right:0;bottom:0;z-index:2147483647",
        "pointer-events:none;box-sizing:border-box",
        "font:600 14px/1.45 ui-sans-serif,system-ui,-apple-system,sans-serif",
        "background:rgba(13,17,23,.95);color:#e6edf3",
        "padding:10px 16px;border-top:2px solid #1f6feb",
        "display:flex;gap:12px;align-items:baseline",
      ].join(";");
      document.body.appendChild(el);
    }
    el.innerHTML = html;
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", draw);
  } else {
    draw();
  }
}

// Paint `html` into the caption bar AND arm it for every subsequent navigation.
// addInitScript accumulates (one script per call, all re-run on each new
// document); they run in insertion order and each sets the same element's
// innerHTML, so the last-painted caption wins — the intended behaviour.
export async function showCaption(page: Page, html: string): Promise<void> {
  await page.addInitScript(paintCaption, html);
  await page.evaluate(paintCaption, html);
}

export async function clearCaption(page: Page): Promise<void> {
  await page.evaluate(() => document.getElementById("__e2e_caption__")?.remove());
}

// Open a recording with a full-screen card that previews the scenario as a
// Given/When/Then plan and lists the spec requirements it verifies, so the video
// states up front exactly what is being tested and how.
export async function introCard(
  page: Page,
  scenarioId: string,
  plan: PlanLine[],
  holdMs = 1000,
): Promise<void> {
  if (!RECORDING) return;
  const s = scenario(scenarioId);
  const title = esc(`${s.id} · ${s.title}`);
  const planLines = plan.map((p) => ({
    keyword: esc(p.keyword),
    color: KEYWORD_COLOR[p.keyword] ?? "#6e7681",
    text: esc(p.text),
    req: p.req ? esc(p.req) : "",
  }));
  const reqs = scenarioRequirements(scenarioId).map((r) => ({
    id: esc(r.id),
    spec: esc(r.spec),
    title: esc(r.title),
    text: esc(r.text),
  }));
  await page.evaluate(
    ({ title, planLines, reqs }) => {
      const card = document.createElement("div");
      card.id = "__e2e_card__";
      card.style.cssText = [
        "position:fixed;inset:0;z-index:2147483647;pointer-events:none",
        "background:#0d1117;color:#e6edf3;overflow:hidden",
        "font:14px/1.5 ui-sans-serif,system-ui,-apple-system,sans-serif",
        "padding:40px 56px;display:flex;flex-direction:column;gap:18px",
      ].join(";");
      const label = (t: string) =>
        '<div style="color:#8b949e;font-size:11px;letter-spacing:.12em;' +
        'text-transform:uppercase">' +
        t +
        "</div>";
      const planRows = planLines
        .map(
          (p) =>
            '<div style="display:flex;gap:12px;align-items:baseline">' +
            '<span style="background:' +
            p.color +
            ";color:#fff;padding:2px 9px;border-radius:4px;font-weight:700;" +
            'font-size:12px;min-width:52px;text-align:center">' +
            p.keyword +
            "</span>" +
            '<span style="font-size:14px">' +
            p.text +
            (p.req
              ? '<span style="color:#8b949e"> · ' + p.req + "</span>"
              : "") +
            "</span></div>",
        )
        .join("");
      const reqRows = reqs
        .map(
          (r) =>
            '<div style="display:flex;gap:12px;align-items:flex-start">' +
            '<span style="background:#1f6feb;color:#fff;padding:2px 8px;border-radius:4px;' +
            'font-weight:700;font-size:12px;white-space:nowrap">' +
            r.id +
            "</span>" +
            '<div style="color:#8b949e;font-size:12px">openspec/specs/' +
            r.spec +
            (r.title ? " · " + r.title : "") +
            "</div></div>",
        )
        .join("");
      card.innerHTML =
        '<div style="color:#8b949e;font-size:11px;letter-spacing:.12em;' +
        'text-transform:uppercase">bundlemcp end-to-end test</div>' +
        '<div style="font-size:22px;font-weight:700;line-height:1.3">' +
        title +
        "</div>" +
        '<div style="height:1px;background:#30363d"></div>' +
        label("Scenario") +
        '<div style="display:flex;flex-direction:column;gap:8px">' +
        planRows +
        "</div>" +
        label("Verifies") +
        '<div style="display:flex;flex-direction:column;gap:6px">' +
        reqRows +
        "</div>";
      document.body.appendChild(card);
    },
    { title, planLines, reqs },
  );
  await page.waitForTimeout(holdMs + (planLines.length + reqs.length) * 700);
  await page.evaluate(() => document.getElementById("__e2e_card__")?.remove());
}
