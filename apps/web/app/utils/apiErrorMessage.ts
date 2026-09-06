/** The message to show for a failed management-API call, from FastAPI's error shape. */
export function apiErrorMessage(err: unknown): string {
  const d = (err as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => (e as { msg?: string }).msg ?? JSON.stringify(e)).join("; ");
  }
  return "Request failed";
}
