/** Badge colour for a server's health status. */
export function healthColor(status: string): "success" | "error" | "neutral" {
  if (status === "ok") return "success";
  if (status === "error") return "error";
  return "neutral";
}
