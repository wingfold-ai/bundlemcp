## MODIFIED Requirements

### Requirement: AUTH-13 Client ID Metadata Documents
A `client_id` that is an `https://` URL SHALL identify a client by its metadata document. The authorize endpoint
fetches the document (through the egress policy, [SEC-1](../security/spec.md)), requires its `client_id` to echo the
URL, validates `redirect_uris` against it (the AUTH-2 rule, including a configured allow-list), and caches it for its
`Cache-Control` lifetime (bounded, default 1 h) in the RESP store. Such clients need no registration: the document is
mirrored into the client table when a signed-in user authorizes, so codes, tokens and consent bind to it; the
pre-login check of the request writes nothing. Consent (AUTH-11) shows the document's `client_name`. Advertised via
`client_id_metadata_document_supported: true` in AUTH-1 metadata. Grant types in the document that the gateway does not
implement (claude.ai lists `urn:ietf:params:oauth:grant-type:jwt-bearer`) are ignored, not refused; a document left
without `authorization_code` is refused at authorize per AUTH-4. A document that arrives but fails validation is
reported as invalid, distinct from one that could not be fetched.

Because anyone can trigger the fetch before signing in, it is narrower than other egress. It connects only to globally
routable addresses: private, loopback, link-local, shared (CGNAT), unique-local, documentation and address-translation
ranges are refused, judged at connect time like SEC-2, unless an explicit `BUNDLEMCP_EGRESS_ALLOW_CIDRS` entry allows
the address. It is bounded: a body larger than 16 KiB is refused without being read further, and the whole fetch,
from connect to the last byte, must finish within 5 seconds. A fetch that fails or yields an invalid document is
remembered for 60 seconds, during which the same URL is refused without fetching again.

#### Scenario: URL client authorizes without registration
- **WHEN** a client whose `client_id` is the https URL of a valid metadata document starts an authorize request
- **THEN** the gateway fetches the document, validates the redirect URI against it, and shows consent naming its
  `client_name`
- **AND** the client is stored only once a signed-in user authorizes

#### Scenario: Document whose client_id does not echo the URL
- **WHEN** the fetched document's `client_id` differs from the URL it was fetched from
- **THEN** the authorize request is refused as an invalid client metadata document, not as an unreachable one

#### Scenario: Unknown grant types are ignored
- **WHEN** the document lists `authorization_code` and the `jwt-bearer` grant
- **THEN** the authorize request proceeds and only `authorization_code` and `refresh_token` are honoured

#### Scenario: A document on a private address is not fetched
- **WHEN** an unauthenticated caller starts an authorize request whose `client_id` URL resolves to `10.0.0.5`
- **THEN** no connection to `10.0.0.5` is made and the request is refused as a client metadata document that could
  not be fetched

#### Scenario: An explicitly allowed address is fetched
- **GIVEN** `BUNDLEMCP_EGRESS_ALLOW_CIDRS` contains `10.0.0.0/24`
- **WHEN** a `client_id` URL resolves to `10.0.0.5` and serves a valid document
- **THEN** the document is fetched and the authorize request proceeds

#### Scenario: An oversized document is refused
- **WHEN** the `client_id` URL answers with a body larger than 16 KiB
- **THEN** the gateway stops reading and refuses the request as a document that could not be fetched

#### Scenario: A slow document is cut off
- **WHEN** the `client_id` URL sends its body a few bytes at a time and is not finished after 5 seconds
- **THEN** the fetch is abandoned and the request is refused

#### Scenario: A failed fetch is not repeated at once
- **GIVEN** a fetch of a `client_id` URL failed less than 60 seconds ago
- **WHEN** another authorize request names the same URL
- **THEN** it is refused without a new request to that URL

## ADDED Requirements

### Requirement: AUTH-34 Metadata-document clients can be turned off
`BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED` (default `true`) SHALL decide whether the gateway accepts `https://`
client ids (AUTH-13). When it is `false`, AUTH-1 metadata advertises `client_id_metadata_document_supported: false`,
and an authorize request with such a `client_id` is refused as an unknown client without any outbound request.
Dynamically registered clients (AUTH-2) are unaffected.

#### Scenario: Turned off, no fetch happens
- **GIVEN** `BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED=false`
- **WHEN** an authorize request names `client_id=https://client.example/meta.json`
- **THEN** it is refused as an unknown client and no request is made to `client.example`

#### Scenario: Turned off, metadata says so
- **GIVEN** `BUNDLEMCP_CLIENT_METADATA_DOCUMENTS_ENABLED=false`
- **WHEN** a client reads `/.well-known/oauth-authorization-server`
- **THEN** `client_id_metadata_document_supported` is `false`

#### Scenario: Default stays on
- **WHEN** the setting is not configured and a client reads the authorization server metadata
- **THEN** `client_id_metadata_document_supported` is `true`
