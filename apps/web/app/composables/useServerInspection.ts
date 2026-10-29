import type { components } from "~~/types/api";

type ServerInspection = components["schemas"]["ServerInspection"];
type ServerJsonDraft = components["schemas"]["ServerJsonDraft"];

/** The registration fields an inspection or a server.json fills in, unless the operator chose them. */
export interface InspectedFields {
  name: Ref<string>;
  /** A name typed by hand is never replaced by a suggestion. */
  nameEdited: Ref<boolean>;
  description: Ref<string>;
  source: Ref<CredentialSource>;
  headerName: Ref<string>;
  presetIndex: Ref<number>;
  sendIdentityHeader: Ref<boolean>;
  /** An explicit choice of the identity header outlives any default. */
  identityHeaderTouched: Ref<boolean>;
  /** The credential header the operator entered, for testing it against the upstream. */
  credentialHeaders: () => Record<string, string>;
}

/** The credential source an inspection's connection state points to, which the form pre-selects. */
const DETECTED_SOURCE: Record<string, CredentialSource> = {
  ready: "none",
  oauth_required: "per_user",
  credential_required: "key",
};

/**
 * The first step of registering an upstream: its URL, checked by the gateway,
 * or a registry server.json, and what either says about the rest of the form.
 * `inspect` and `importServerJson` return the API's result or throw a
 * `ValidationProblem`, for the card's action to show.
 */
export function useServerInspection(fields: InspectedFields) {
  const api = useApi();
  const url = ref("");
  const serverJson = ref("");
  const showServerJson = ref(false);
  const draft = ref<ServerJsonDraft | null>(null);
  const inspecting = ref(false);
  const inspection = ref<ServerInspection | null>(null);
  /** The details form, open after a check or on request. */
  const detailsOpen = ref(false);
  /** What the check without a credential found; a later credential test does not change it. */
  const detectedSource = ref<CredentialSource | null>(null);
  /** The answer to the last credential test, cleared whenever the credential changes. */
  const verified = ref<"" | "ok" | "refused">("");

  /** Take the server's own name and description, unless the operator typed their own. */
  function suggestName(result: ServerInspection) {
    if (!fields.nameEdited.value) fields.name.value = result.suggestion.name;
    if (result.suggestion.description && !fields.description.value)
      fields.description.value = result.suggestion.description;
  }

  /** Pre-select what the inspection found. */
  function applyInspection(result: ServerInspection) {
    if (result.suggested_url) url.value = result.suggested_url;
    suggestName(result);
    const detected = DETECTED_SOURCE[result.connection_state] ?? null;
    detectedSource.value = detected;
    if (!fields.identityHeaderTouched.value)
      fields.sendIdentityHeader.value = result.suggestion.send_identity_header ?? false;
    // a key already entered (from a server.json) stays chosen when the server answers anyway
    if (detected && !(detected === "none" && fields.source.value === "key"))
      fields.source.value = detected;
  }

  async function inspect(withCredential = false) {
    if (!url.value.trim()) throw new ValidationProblem("Enter the upstream's URL first");
    inspecting.value = true;
    try {
      const result = await api.POST("/api/v1/upstreams:inspect", {
        body: { url: url.value.trim(), headers: withCredential ? fields.credentialHeaders() : {} },
      });
      const data = result.data;
      if (!data) return result;
      inspection.value = data;
      if (withCredential) {
        verified.value = data.connection_state === "ready" ? "ok" : "refused";
        suggestName(data); // the server can name itself once it lets us in
      } else {
        applyInspection(data);
      }
      detailsOpen.value = true;
      return result;
    } finally {
      inspecting.value = false;
    }
  }

  async function importServerJson() {
    let document: Record<string, unknown>;
    try {
      document = JSON.parse(serverJson.value);
    } catch {
      throw new ValidationProblem("server.json is not valid JSON");
    }
    const result = await api.POST("/api/v1/upstreams:from-server-json", { body: { document } });
    const data = result.data;
    if (!data) return result;
    draft.value = data;
    fields.name.value = data.name;
    fields.nameEdited.value = true; // the publisher's name wins over the one serverInfo reports
    fields.description.value = data.description ?? "";
    if (data.url) url.value = data.url;
    const headers = data.headers ?? [];
    const header = headers.find((h) => h.is_required) ?? headers[0];
    if (header) {
      fields.source.value = "key";
      fields.headerName.value = header.name;
      const preset = CREDENTIAL_HEADER_PRESETS.findIndex(
        (p) => p.name.toLowerCase() === header.name.toLowerCase(),
      );
      fields.presetIndex.value = preset < 0 ? CREDENTIAL_HEADER_PRESETS.length - 1 : preset;
    }
    showServerJson.value = false;
    if (data.url && !data.url_variables?.length) return await inspect();
    detailsOpen.value = true;
    return result;
  }

  return {
    url,
    serverJson,
    showServerJson,
    draft,
    inspecting,
    inspection,
    detailsOpen,
    detectedSource,
    verified,
    inspect,
    importServerJson,
  };
}
