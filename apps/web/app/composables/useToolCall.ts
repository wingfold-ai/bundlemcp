import type { components } from "~~/types/api";

type Schemas = components["schemas"];
type Target = Schemas["InspectorRequest"]["target"];
type Progress = Schemas["InspectorProgress"];
type Outcome = Schemas["InspectorCallOutcome"];
type Failure = Schemas["InspectorFailure"];

/**
 * One tool call from the inspector, streamed: the progress the tool reports
 * while it runs, then either its outcome or why the gateway could not call it.
 */
export function useToolCall() {
  const calling = ref(false);
  const progress = ref<Progress[]>([]);
  const outcome = ref<Outcome | null>(null);
  const failure = ref<Failure | null>(null);

  function reset() {
    progress.value = [];
    outcome.value = null;
    failure.value = null;
  }

  /** Call `tool` on `target`; resolves to the message to show when the call could not be made. */
  async function call(
    target: Target,
    tool: string,
    args: Record<string, unknown>,
  ): Promise<string | null> {
    reset();
    calling.value = true;
    try {
      // a POST answered with an event stream: read it with fetch, since EventSource only GETs
      const response = await authedFetch("/api/v1/inspector:call-tool", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
        body: JSON.stringify({ target, tool, arguments: args }),
      });
      // the session handling has already sent the browser to sign in again
      if (response.status === 401) return null;
      if (!response.ok || !response.body) {
        return apiErrorMessage(await response.json().catch(() => null));
      }
      for await (const event of serverSentEvents(response.body)) {
        const data = JSON.parse(event.data);
        if (event.event === "progress") progress.value.push(data as Progress);
        else if (event.event === "result") outcome.value = data as Outcome;
        else if (event.event === "failure") failure.value = data as Failure;
      }
      return null;
    } catch {
      return "The call's stream was interrupted.";
    } finally {
      calling.value = false;
    }
  }

  return { calling, progress, outcome, failure, reset, call };
}
