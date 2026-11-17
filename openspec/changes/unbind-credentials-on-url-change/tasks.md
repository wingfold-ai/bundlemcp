# Tasks

## 1. Domain

- [x] 1.1 Add `UrlChange` (`domain/servers/url_change.py`) with `moves_resource` and `moves_origin`; verify with unit
  tests covering case, trailing slash, default ports, path and host changes
- [x] 1.2 Add `UpstreamClientMetadata.forgetting_server()`; verify a unit test that endpoints and step-up scopes are
  gone and identification, grant and unknown keys stay

## 2. Revocation on a resource change (UPS-41)

- [x] 2.1 Add `UpstreamCredentialRevocation` and call it from `ServerService.upsert` when the resource moves; verify
  application tests citing UPS-41: tokens deleted, gateway-obtained client deleted, admin client trimmed, audit record
  written with the actor, nothing revoked for a case or slash change, nothing revoked when the write is refused
- [x] 2.2 Pass the principal from `ServerController.upsert_server`; verify an API test citing UPS-41 that the audit
  record carries the admin's user id and that a `per_user` caller is offered the connect tool after the change

## 3. Secrets on an origin change (UPS-42)

- [x] 3.1 Refuse an origin move without static header values, and clear an admin client's secret on an origin move;
  verify application tests citing UPS-42 for the refusal, a re-entered header, a same-origin path change and the
  cleared secret
- [x] 3.2 Refuse a static header placeholder across an origin move in the import, and pass the principal through the
  import route; verify an import test citing UPS-42 that reports the upstream as an error and changes nothing

## 4. Documentation

- [x] 4.1 Add a "Changing a server's URL" section to `docs/manage/servers.md`; verify
      `python3 tools/check_docs_links.py` and `check_docs_settings.py` pass

## 5. Gates

- [x] 5.1 Run `uv run pytest -q`, `uv run ruff check .`, `uv run rumdl check .`, `uv run lint-imports`, the four
  `tools/check_*.py` scripts, `python3 tools/check_spec_ids.py` and `openspec validate --all --strict`; all pass
