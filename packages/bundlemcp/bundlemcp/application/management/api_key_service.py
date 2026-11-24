"""API key business logic."""

import uuid

import structlog

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import ConflictError, ForbiddenError, NotFoundError
from bundlemcp.application.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
from bundlemcp.domain.access.api_key_scope import ApiKeyScope
from bundlemcp.domain.access.principal import Principal
from bundlemcp.domain.shared.secret_generator import SecretGenerator
from bundlemcp.domain.shared.secret_hasher import SecretHasher
from bundlemcp.domain.shared.secrets import API_KEY_PREFIX, display_prefix

log = structlog.get_logger(__name__)


class ApiKeyService:
    def __init__(
        self, uow: UnitOfWork, *, hasher: SecretHasher, generator: SecretGenerator
    ) -> None:
        self._uow = uow
        self._keys = uow.api_keys
        self._hasher = hasher
        self._generator = generator

    async def _get(self, key_id: uuid.UUID) -> ApiKey:
        key = await self._keys.get(key_id)
        if key is None:
            raise NotFoundError("key not found")
        return key

    def _invalidate(self, key_id: uuid.UUID, action: str) -> None:
        self._uow.invalidate(
            InvalidationEvent(entity_type="api_key", key=str(key_id), action=action)  # type: ignore[arg-type]
        )

    async def list(self, *, offset: int, limit: int) -> Page[ApiKeyRead]:
        page_slice = await self._keys.page(offset=offset, limit=limit)
        return Page.of(page_slice, offset=offset, limit=limit, read=ApiKeyRead.from_entity)

    async def create(self, body: ApiKeyCreate, actor: Principal | None = None) -> ApiKeyCreated:
        """The key value is returned exactly once; only the hash is stored.

        A scoped caller may only create a service key whose scopes it holds itself, so
        ``keys:manage`` never grants more than its holder has.
        """
        _within_reach(actor, body.kind, body.scopes)
        if await self._keys.by_name(body.name) is not None:
            raise ConflictError(f"an API key named {body.name!r} already exists (AUTH-23)")
        value = self.new_value()
        key = self._keys.add(
            self._key(body.name, body.kind, [str(e) for e in body.endpoint_ids], value, body.scopes)
        )
        await self._uow.commit()
        await self._uow.refresh(key)
        return ApiKeyCreated(**ApiKeyRead.from_entity(key).model_dump(), key=value)

    def new_value(self) -> str:
        """A fresh key value in the ``bmcp_sk_`` format."""
        return API_KEY_PREFIX + self._generator.token(32)

    def _key(
        self,
        name: str,
        kind: ApiKeyKind,
        endpoint_ids: list[str],
        value: str,
        scopes: list[ApiKeyScope] | None = None,
    ) -> ApiKey:
        return ApiKey(
            name=name,
            key_hash=self._hasher.digest(value),
            key_prefix=display_prefix(value),
            kind=kind,
            endpoint_ids=endpoint_ids,
            scopes=sorted(set(scopes or [])),
        )

    async def exists(self, name: str) -> bool:
        return await self._keys.by_name(name) is not None

    def provision(
        self,
        name: str,
        kind: ApiKeyKind,
        endpoint_ids: list[str],
        value: str,
        *,
        scopes: list[ApiKeyScope] | None = None,
    ) -> None:
        """Store a key with a value supplied from outside, in the caller's transaction.

        The caller decides that no key of that name exists; the value itself is
        hashed and never kept.
        """
        self._keys.add(self._key(name, kind, endpoint_ids, value, scopes))

    async def ensure_initial_service_key(self, value: str) -> bool:
        """Provision the operator-supplied service key unless a service key already exists.

        Returns whether a key was created.
        """
        existing = await self._keys.any_of_kind(ApiKeyKind.SERVICE)
        if existing is not None:
            return False
        self._keys.add(
            ApiKey(
                name="initial-service-key",
                key_hash=self._hasher.digest(value),
                key_prefix=display_prefix(value),
                kind=ApiKeyKind.SERVICE,
            )
        )
        await self._uow.commit()
        log.info("bootstrap.initial_service_key_created")
        return True

    async def deactivate(self, key_id: uuid.UUID, actor: Principal | None = None) -> ApiKeyRead:
        """Takes effect via a published invalidation event, not cache TTL."""
        key = await self._get(key_id)
        _within_reach(actor, key.kind, key.scopes)
        key.is_active = False
        self._keys.add(key)
        self._invalidate(key_id, "updated")
        await self._uow.commit()
        await self._uow.refresh(key)
        return ApiKeyRead.from_entity(key)

    async def activate(self, key_id: uuid.UUID, actor: Principal | None = None) -> ApiKeyRead:
        """Accept a deactivated key again, on every replica once the invalidation event lands."""
        key = await self._get(key_id)
        _within_reach(actor, key.kind, key.scopes)
        key.is_active = True
        self._keys.add(key)
        self._invalidate(key_id, "updated")
        await self._uow.commit()
        await self._uow.refresh(key)
        return ApiKeyRead.from_entity(key)

    async def delete(self, key_id: uuid.UUID, actor: Principal | None = None) -> None:
        key = await self._keys.get(key_id)
        if key is None:
            return
        _within_reach(actor, key.kind, key.scopes)
        await self._keys.delete(key)
        self._invalidate(key_id, "deleted")
        await self._uow.commit()


def _within_reach(
    actor: Principal | None, kind: ApiKeyKind, scopes: list[ApiKeyScope] | list[str]
) -> None:
    """A scoped caller acts only on scoped service keys whose scopes it holds itself.

    An admin, an unscoped service key and an internal caller (``actor`` None) act on every
    key. A scoped caller can never create, (de)activate or delete an endpoint key, a full
    service key, or a key with a scope it lacks.
    """
    if actor is None or not actor.scopes:
        return
    held = set(actor.scopes)
    wanted = {str(s) for s in scopes}
    if kind is not ApiKeyKind.SERVICE or not wanted or not wanted <= held:
        raise ForbiddenError(
            "a scoped key may only manage service keys whose scopes it holds itself (AUTH-40)"
        )
