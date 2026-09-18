/** How a server's negotiated MCP revision and its negotiation mode are shown. */

export interface ProtocolLabel {
  /** The revision to print, or "—" when the server has not been reached yet. */
  text: string;
  /** Why that is the value, for the badge's title attribute. */
  help: string;
  /** True once a revision has actually been negotiated. */
  known: boolean;
  /** Set when the mode is worth showing beside the revision. */
  mode: string | null;
}

/**
 * A server carries the revision it last negotiated (protocol_version) and the rule
 * the gateway follows when negotiating (protocol_mode). The revision is what an
 * operator wants to read; the mode only earns space when it is not the default
 * "auto", because then it explains the revision.
 */
export function protocolLabel(
  protocolVersion: string | null | undefined,
  protocolMode: string | null | undefined,
): ProtocolLabel {
  const mode = protocolMode && protocolMode !== "auto" ? protocolMode : null;
  if (!protocolVersion) {
    return {
      text: "—",
      help: "No revision negotiated yet: the server has not been probed successfully",
      known: false,
      mode,
    };
  }
  return {
    text: protocolVersion,
    help:
      mode === null
        ? `MCP revision ${protocolVersion}, negotiated at the last successful probe`
        : `MCP revision ${protocolVersion}, negotiated with protocol mode '${mode}'`,
    known: true,
    mode,
  };
}
