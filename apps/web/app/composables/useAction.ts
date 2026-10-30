/**
 * A rule the form checks before anything is sent, broken. Thrown from an
 * action, it is shown where an API refusal would be, on the card that ran it.
 */
export class ValidationProblem extends Error {}

/** What an action returns: an `openapi-fetch` result, or nothing when it has no single call. */
type ActionResult = { error?: unknown } | void;

/**
 * One button's action on a card, with the card's own busy flag and error.
 *
 * `run` clears the previous error, then awaits `fn`. A thrown
 * `ValidationProblem` or a result carrying an `error` becomes the message in
 * `error`; on success the cached reads of `invalidates` are marked stale.
 * `run` resolves to whether the action succeeded, so a caller can go on with
 * what only follows a success, such as navigating away.
 */
export function useAction<Args extends unknown[]>(
  fn: (...args: Args) => Promise<ActionResult>,
  options: { invalidates?: MaybeRefOrGetter<string[]> } = {},
) {
  const busy = ref(false);
  const error = ref("");

  async function run(...args: Args): Promise<boolean> {
    error.value = "";
    busy.value = true;
    try {
      const result = await fn(...args);
      if (result && result.error !== undefined) {
        error.value = apiErrorMessage(result.error);
        return false;
      }
      const stale = toValue(options.invalidates) ?? [];
      if (stale.length) await invalidate(...stale);
      return true;
    } catch (thrown) {
      if (thrown instanceof ValidationProblem) {
        error.value = thrown.message;
        return false;
      }
      throw thrown;
    } finally {
      busy.value = false;
    }
  }

  return { run, busy, error };
}

/**
 * One action shared by every button of a card: each button passes the call it
 * makes to `run`, so the card has one busy flag and one error, and starting
 * any of its actions clears whatever the last one left.
 */
export function useCardAction(options: { invalidates?: MaybeRefOrGetter<string[]> } = {}) {
  return useAction((call: () => Promise<ActionResult>) => call(), options);
}
