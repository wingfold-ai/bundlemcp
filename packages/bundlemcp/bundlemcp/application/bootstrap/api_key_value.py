"""Where a bootstrapped API key's value comes from, and how a generated one is handed over."""

import os
from collections.abc import Callable, Mapping
from pathlib import Path

from bundlemcp.application.bootstrap.bootstrap_api_key import BootstrapApiKey
from bundlemcp.domain.shared.secrets import API_KEY_FORMAT


class ApiKeyValueUnavailable(ValueError):
    """An entry's value cannot be had. The message names the variable or file, never a value."""


def api_key_value(
    entry: BootstrapApiKey, *, environ: Mapping[str, str], generate: Callable[[], str]
) -> str:
    """The value the key ``entry`` describes is provisioned with.

    A referenced variable must be set and hold a ``bmcp_sk_`` value. A generated
    value is written to the entry's file, created with mode 0600; a file that
    already exists is never overwritten, and its value is used when it holds one.
    """
    if entry.value_from_env is not None:
        value = environ.get(entry.value_from_env)
        if value is None:
            raise ApiKeyValueUnavailable(
                f"api key {entry.name!r}: variable {entry.value_from_env} is not set (MGMT-10)"
            )
        if not API_KEY_FORMAT.match(value):
            raise ApiKeyValueUnavailable(
                f"api key {entry.name!r}: variable {entry.value_from_env} does not hold a "
                "bmcp_sk_ key value (MGMT-10)"
            )
        return value
    assert entry.write_to is not None  # the model requires it with create_if_missing
    path = Path(entry.write_to)
    if path.exists():
        kept = path.read_text().strip()
        if not API_KEY_FORMAT.match(kept):
            raise ApiKeyValueUnavailable(
                f"api key {entry.name!r}: {path} exists without a bmcp_sk_ key value, and an "
                "existing file is never overwritten (MGMT-10)"
            )
        return kept
    value = generate()
    # exclusive and private from the first byte: another writer or reader never sees it
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(value + "\n")
    return value
