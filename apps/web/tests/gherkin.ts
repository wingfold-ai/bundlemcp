import { test as base, type Page } from "@playwright/test";
import { RECORDING, esc, introCard, showCaption, type PlanLine } from "./overlay";
import { requirement } from "./spec-map";

// A Gherkin-style Given/When/Then DSL layered onto Playwright. Tests declare a
// scenario as an array of steps and hand it to `steps.play([...])`, which:
//   1. opens the recording with an intro card previewing the plan + the spec
//      requirements it verifies,
//   2. runs each step inside a `test.step(...)` (so steps show in the HTML
//      report / trace), painting a live caption on the video as it goes.
// Everything video-related is a no-op unless PW_VIDEO=1, so normal runs are
// unchanged and fast.

export { expect } from "@playwright/test";

export type Keyword = "Given" | "When" | "Then" | "And";

type StepOpts = { req?: string };
type StepBody = () => void | Promise<void>;

export interface Step {
  keyword: Keyword;
  text: string;
  req?: string;
  body?: StepBody;
}

const KEYWORD_COLOR: Record<Keyword, string> = {
  Given: "#1f6feb", // setup / context
  When: "#d29922", // driving input
  Then: "#3fb950", // checking output
  And: "#6e7681", // continuation
};

// Discriminate the overloaded call forms:
//   (text) | (text, body) | (text, {req}) | (text, {req}, body)
function build(
  keyword: Keyword,
  text: string,
  optsOrBody?: StepOpts | StepBody,
  body?: StepBody,
): Step {
  const opts = typeof optsOrBody === "function" ? undefined : optsOrBody;
  const fn = typeof optsOrBody === "function" ? optsOrBody : body;
  return { keyword, text, req: opts?.req, body: fn };
}

export function given(text: string, opts?: StepOpts, body?: StepBody): Step;
export function given(text: string, body: StepBody): Step;
export function given(text: string, optsOrBody?: StepOpts | StepBody, body?: StepBody): Step {
  return build("Given", text, optsOrBody, body);
}

export function when(text: string, opts?: StepOpts, body?: StepBody): Step;
export function when(text: string, body: StepBody): Step;
export function when(text: string, optsOrBody?: StepOpts | StepBody, body?: StepBody): Step {
  return build("When", text, optsOrBody, body);
}

export function then(text: string, opts?: StepOpts, body?: StepBody): Step;
export function then(text: string, body: StepBody): Step;
export function then(text: string, optsOrBody?: StepOpts | StepBody, body?: StepBody): Step {
  return build("Then", text, optsOrBody, body);
}

export function and(text: string, opts?: StepOpts, body?: StepBody): Step;
export function and(text: string, body: StepBody): Step;
export function and(text: string, optsOrBody?: StepOpts | StepBody, body?: StepBody): Step {
  return build("And", text, optsOrBody, body);
}

function stepHtml(s: Step): string {
  const badge =
    '<span style="background:' +
    KEYWORD_COLOR[s.keyword] +
    ";color:#fff;padding:2px 9px;border-radius:4px;font-size:13px;font-weight:700;" +
    'white-space:nowrap">' +
    s.keyword +
    "</span>";
  const spec = s.req
    ? '<span style="color:#8b949e;font-weight:400"> — spec/' +
      esc(requirement(s.req).spec) +
      "</span>"
    : "";
  return badge + '<span style="flex:1">' + esc(s.text) + spec + "</span>";
}

export class Stepper {
  constructor(private readonly page: Page) {}

  // Render the intro card from the plan, then run each step: a live caption
  // (recording only) followed by the step body, wrapped in test.step so it
  // appears in the report/trace and failures are localised to the step.
  async play(plan: Step[]): Promise<void> {
    const id = base.info().title.match(/E2E-\d+/)?.[0];
    if (id) {
      const lines: PlanLine[] = plan.map(({ keyword, text, req }) => ({ keyword, text, req }));
      await introCard(this.page, id, lines);
    }
    for (const s of plan) {
      await base.step(`${s.keyword}: ${s.text}`, async () => {
        if (RECORDING) {
          await showCaption(this.page, stepHtml(s));
          await this.page.waitForTimeout(600); // hold long enough to read
        }
        if (s.body) await s.body();
      });
    }
  }
}

export const test = base.extend<{ steps: Stepper }>({
  steps: async ({ page }, use) => {
    await use(new Stepper(page));
  },
});
