/** One row of a header editor: a header name and what it maps to. */
export interface HeaderRow {
  key: string;
  val: string;
}

/**
 * How a row with an empty value is sent: `"keep"` sends the empty value as
 * typed; `"key"` sends the row's own name, so a forwarded header keeps its name
 * at the upstream.
 */
export type EmptyHeaderValue = "keep" | "key";

/** The header map a list of rows stands for: rows without a name are left out, names are trimmed. */
export function rowsToHeaders(
  rows: HeaderRow[],
  options: { emptyValue: EmptyHeaderValue },
): Record<string, string> {
  const headers: Record<string, string> = {};
  for (const row of rows) {
    const key = row.key.trim();
    if (!key) continue;
    headers[key] = row.val || (options.emptyValue === "key" ? row.key : row.val);
  }
  return headers;
}

/** The rows that edit a stored header map. */
export function headersToRows(headers: Record<string, string>): HeaderRow[] {
  return Object.entries(headers).map(([key, val]) => ({ key, val }));
}
