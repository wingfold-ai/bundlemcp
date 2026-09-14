/** Where an upstream server sits relative to the gateway, read off its URL. */
export interface ConnectionKind {
  /** `local`: a hostname the compose or cluster network resolves (no dots,
   * `localhost`, `.local`/`.internal`, or a private IP). `external`: a public host. */
  network: "local" | "external";
  scheme: "http" | "https" | "other";
}

const PRIVATE_IPV4 = /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/;

export function connectionKind(url: string): ConnectionKind {
  let host = "";
  let scheme: ConnectionKind["scheme"] = "other";
  try {
    const parsed = new URL(url);
    host = parsed.hostname.toLowerCase();
    scheme = parsed.protocol === "https:" ? "https" : parsed.protocol === "http:" ? "http" : "other";
  } catch {
    return { network: "external", scheme };
  }
  const local =
    host === "localhost" ||
    !host.includes(".") ||
    host.endsWith(".local") ||
    host.endsWith(".internal") ||
    host.endsWith(".svc") ||
    host.endsWith(".svc.cluster.local") ||
    PRIVATE_IPV4.test(host);
  return { network: local ? "local" : "external", scheme };
}
