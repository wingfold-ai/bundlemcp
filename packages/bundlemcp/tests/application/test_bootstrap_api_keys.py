"""API keys provisioned by the bootstrap document (MGMT-8, MGMT-9, MGMT-10, SEC-10)."""

import os
import stat

import pytest
from bundlemcp.application.bootstrap.api_key_value import ApiKeyValueUnavailable
from bundlemcp.application.bootstrap.bootstrap_document import BootstrapDocument
from bundlemcp.application.bootstrap.bootstrap_runner import BootstrapRunner
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.endpoints.profiles import ProfileCatalog
from bundlemcp.domain.shared.sha256_secret_hasher import Sha256SecretHasher
from bundlemcp.infrastructure.memory.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
    InMemoryUnitOfWorkFactory,
)
from bundlemcp.infrastructure.memory.no_upstream_connections import NoUpstreamConnections
from bundlemcp.infrastructure.memory.noop_tool_discovery import NoopToolDiscovery
from bundlemcp.infrastructure.memory.sequential_secret_generator import SequentialSecretGenerator
from pydantic import ValidationError
from structlog.testing import capture_logs

REGISTRAR = "bmcp_sk_" + "r" * 43
HASHER = Sha256SecretHasher()


def _runner(uow: InMemoryUnitOfWork, environ: dict[str, str] | None = None) -> BootstrapRunner:
    return BootstrapRunner(
        InMemoryUnitOfWorkFactory(uow),
        NoopToolDiscovery(),
        cipher=None,
        connections=NoUpstreamConnections(),
        profiles=ProfileCatalog.builtin(),
        public_base="http://gw",
        hasher=HASHER,
        generator=SequentialSecretGenerator(),
        environ=environ or {},
    )


def _document(*keys: dict, endpoints: bool = True) -> BootstrapDocument:
    return BootstrapDocument.model_validate(
        {
            "bundles": [{"name": "demo"}] if endpoints else [],
            "endpoints": [{"name": "demo", "bundle_name": "demo", "auth_modes": ["api_key"]}]
            if endpoints
            else [],
            "api_keys": list(keys),
        }
    )


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


def test_mgmt8_a_document_declares_api_keys():
    """MGMT-8: an api_keys entry validates."""
    doc = _document({"name": "registrar", "kind": "service", "value_from_env": "REGISTRAR_KEY"})
    assert [key.name for key in doc.api_keys] == ["registrar"]


@pytest.mark.parametrize(
    "entry",
    [
        {"name": "inline", "key": REGISTRAR},  # a value in the document
        {"name": "both", "value_from_env": "X", "create_if_missing": True, "write_to": "/k"},
        {"name": "neither"},
        {"name": "nowhere", "create_if_missing": True},
        {"name": "service", "kind": "service", "endpoints": ["demo"], "value_from_env": "X"},
    ],
)
def test_mgmt10_an_entry_without_exactly_one_source_is_refused(entry):
    """MGMT-10: an inline value, both sources or none, or a scoped service key fail validation."""
    with pytest.raises(ValidationError):
        _document(entry)


async def test_mgmt10_a_key_from_an_environment_reference(uow):
    """MGMT-10: the referenced value authenticates, and only its hash is stored."""
    doc = _document({"name": "registrar", "kind": "service", "value_from_env": "REGISTRAR_KEY"})
    await _runner(uow, {"REGISTRAR_KEY": REGISTRAR}).apply(doc)
    key = await uow.api_keys.by_name("registrar")
    assert key is not None and key.kind is ApiKeyKind.SERVICE
    assert await uow.api_keys.by_hash(HASHER.digest(REGISTRAR)) == key
    assert REGISTRAR not in key.model_dump_json()


@pytest.mark.parametrize("environ", [{}, {"REGISTRAR_KEY": "not-a-key"}])
async def test_mgmt10_a_missing_or_malformed_reference_does_not_land(uow, environ):
    """MGMT-10: the document does not land, and the error names the variable, not a value."""
    doc = _document({"name": "registrar", "kind": "service", "value_from_env": "REGISTRAR_KEY"})
    with pytest.raises(ApiKeyValueUnavailable) as raised:
        await _runner(uow, environ).apply(doc)
    assert "REGISTRAR_KEY" in str(raised.value)
    assert "not-a-key" not in str(raised.value)
    assert await uow.api_keys.by_name("registrar") is None
    assert await uow.endpoints.by_name("demo") is None


async def test_mgmt10_a_generated_key_is_written_to_its_file_once(uow, tmp_path):
    """MGMT-10, SEC-10: the value lands in a 0600 file and in no log line; next start, nothing."""
    target = tmp_path / "ci.key"
    entry = {
        "name": "ci",
        "endpoints": ["demo"],
        "create_if_missing": True,
        "write_to": str(target),
    }
    with capture_logs() as logs:
        await _runner(uow).apply(_document(entry))
    value = target.read_text().strip()
    assert stat.S_IMODE(os.stat(target).st_mode) == 0o600
    key = await uow.api_keys.by_name("ci")
    endpoint = await uow.endpoints.by_name("demo")
    assert key is not None and endpoint is not None
    assert key.endpoint_ids == [str(endpoint.id)]
    assert await uow.api_keys.by_hash(HASHER.digest(value)) == key
    assert value not in repr(logs)

    written = target.stat().st_mtime_ns
    await _runner(uow).apply(_document(entry))
    assert target.stat().st_mtime_ns == written and target.read_text().strip() == value


async def test_mgmt10_an_existing_file_is_reused_not_overwritten(uow, tmp_path):
    """MGMT-10: a file holding a key value supplies it when no key of that name exists."""
    target = tmp_path / "ci.key"
    target.write_text(REGISTRAR + "\n")
    entry = {"name": "ci", "create_if_missing": True, "write_to": str(target)}
    await _runner(uow).apply(_document(entry))
    assert await uow.api_keys.by_hash(HASHER.digest(REGISTRAR)) is not None
    assert target.read_text() == REGISTRAR + "\n"


async def test_mgmt10_a_file_without_a_key_value_refuses_the_document(uow, tmp_path):
    """MGMT-10: an unrelated existing file is neither overwritten nor used."""
    target = tmp_path / "ci.key"
    target.write_text("something else")
    entry = {"name": "ci", "create_if_missing": True, "write_to": str(target)}
    with pytest.raises(ApiKeyValueUnavailable):
        await _runner(uow).apply(_document(entry))
    assert target.read_text() == "something else"
    assert await uow.api_keys.by_name("ci") is None


async def test_mgmt10_an_existing_key_is_never_overwritten(uow):
    """MGMT-10, MGMT-9: re-applying, even with another value, kind or scope, changes nothing."""
    doc = _document({"name": "registrar", "kind": "service", "value_from_env": "REGISTRAR_KEY"})
    await _runner(uow, {"REGISTRAR_KEY": REGISTRAR}).apply(doc)
    stored = await uow.api_keys.by_name("registrar")
    assert stored is not None
    stored.is_active = False
    uow.api_keys.add(stored)
    other = _document({"name": "registrar", "endpoints": ["demo"], "value_from_env": "OTHER"})
    await _runner(uow, {"OTHER": "bmcp_sk_" + "o" * 43}).apply(other)
    kept = await uow.api_keys.by_name("registrar")
    assert kept is not None
    assert (kept.key_hash, kept.kind, kept.endpoint_ids, kept.is_active) == (
        HASHER.digest(REGISTRAR),
        ApiKeyKind.SERVICE,
        [],
        False,
    )


async def test_mgmt10_a_scope_naming_an_unknown_endpoint_does_not_land(uow):
    """MGMT-10: an endpoint neither the document nor the store defines refuses the document."""
    doc = _document(
        {"name": "ci", "endpoints": ["nowhere"], "value_from_env": "CI_KEY"}, endpoints=False
    )
    with pytest.raises(ValueError, match="nowhere"):
        await _runner(uow, {"CI_KEY": REGISTRAR}).apply(doc)
    assert await uow.api_keys.by_name("ci") is None
