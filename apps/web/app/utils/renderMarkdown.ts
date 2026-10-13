import DOMPurify from "dompurify";
import { marked } from "marked";

/**
 * A bundle resource's Markdown as sanitized HTML, for the preview (BND-31).
 * The content is written by an administrator but shown to every administrator,
 * so it is sanitized before it reaches `v-html`: a resource cannot run script in
 * another admin's session.
 */
export function renderMarkdown(source: string): string {
  return DOMPurify.sanitize(marked.parse(source, { async: false }));
}
