// the gateway's placeholder rule, mirrored for the preview. One pass over
// the text: a substituted value is never scanned again, and an argument with no
// value becomes the empty string, exactly as prompts/get renders it.
const PLACEHOLDER = /\{\{([a-zA-Z0-9_-]+)\}\}/g;

/** Message text with every `{{argument}}` replaced by its sample value. */
export function renderPromptText(text: string, values: Record<string, string>): string {
  return text.replace(PLACEHOLDER, (_match, name: string) => values[name] ?? "");
}

/** The argument names a message text refers to. */
export function promptPlaceholders(text: string): string[] {
  return [...text.matchAll(PLACEHOLDER)].map((match) => match[1]!);
}
