# Module Naming

A module is named for **what it holds**, never for the kind of Python object
inside it. There is no `_common.py`, no `_functions.py`, no `utils.py`, and no
`helpers.py` in this repo; new code must not reintroduce them.

## Why those names fail

`_functions.py` tells the reader the file contains functions — which they knew.
It names the language construct instead of the subject, so nothing can be found
by guessing a filename, and the file becomes the place anything unassignable
lands.

The failure is observable, not theoretical. The repo previously carried 17 such
files, and the `_common` / `_functions` split had already stopped meaning
anything: three `_common.py` files held functions (`tool_schema_hash`,
`coerce`, `_aware`), while three `_functions.py` files held exactly one
function each. "Where does this new helper go?" had no learnable answer, which
is the definition of a bin.

## One function is enough to justify one file

Prefer a concretely named module over a shared bin, even for a single
definition:

```
gateway/discovery/tool_schema_hash.py     one function
gateway/metering/idempotency_key.py       one function
store/invalidation/publish_invalidation.py one function
```

Keep the leading underscore when the module is package-internal — that is a
privacy marker and it is idiomatic (`httpx` ships `_client.py`, `_config.py`).
Just make the rest of the name say the subject.

## Where a constant or a helper actually belongs

Before creating a module, ask which existing module *owns the concept*. Most
constants have an obvious owner and need no file at all:

| Constant | Owner |
|---|---|
| `RATE_KEY` | `rate_limiter.py` — it is that limiter's key layout |
| `SESSION_RECORD_VERSION` | `session_record.py` — it is that record's schema version |
| `PREFIX_SEP` | `presented_tool.py` — it separates the parts of that name |
| `REFRESH_LOCK_KEY` | `upstream_token_store.py` — it guards that store's refresh |

Same for factories: a function that builds one class belongs beside that class
(`token_cipher` next to `TokenCipher`, `get_settings` next to `Settings`), not
in a separate module of loose functions.

Split a module when it does two jobs, not when it grows: `load_document` (read
YAML into a validated document) and `run_bootstrap` (drive the services) became
`document_loader.py` and `bootstrap_runner.py` because they are two jobs.

## Loggers

`log = structlog.get_logger(...)` is declared in the module that logs. Do not
hoist it into a shared module for the package — a logger reached from another
module is a shared-bin symptom, and a package's logger is never public API.

## Private names are not exported

If a name starts with an underscore it does not appear in `__all__`. Either it
is API and loses the underscore, or it is not and stays out of the package's
export list. Three names (`_apply_profile_annotations`, `_merge_overrides`,
`_CallOutcome`) were exported this way with no consumer at all — not even a
test.
