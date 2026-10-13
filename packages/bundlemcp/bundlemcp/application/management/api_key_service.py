"""API key business logic."""

import uuid

import structlog

from bundlemcp.application.contracts.persistence.invalidation_event import InvalidationEvent
from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWork
from bundlemcp.application.errors import NotFoundError
from bundlemcp.application.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyRead, Page
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.api_key_kind import ApiKeyKind
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
        total, rows = await self._keys.page(offset=offset, limit=limit)
        return Page.of(rows, total, offset=offset, limit=limit, read=ApiKeyRead.from_entity)

    async def create(self, body: ApiKeyCreate) -> ApiKeyCreated:
        """The key value is returned exactly once; only the hash is stored."""
        value = API_KEY_PREFIX + self._generator.token(32)
        key = self._keys.add(
            ApiKey(
                name=body.name,
                key_hash=self._hasher.digest(value),
                key_prefix=display_prefix(value),
                kind=body.kind,
                endpoint_ids=[str(e) for e in body.endpoint_ids],
            )
        )
        await self._uow.commit()
        await self._uow.refresh(key)
        return ApiKeyCreated(**ApiKeyRead.from_entity(key).model_dump(), key=value)

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

    async def deactivate(self, key_id: uuid.UUID) -> ApiKeyRead:
        """Takes effect via a published invalidation event, not cache TTL."""
        key = await self._get(key_id)
        key.is_active = False
        self._keys.add(key)
        self._invalidate(key_id, "updated")
        await self._uow.commit()
        await self._uow.refresh(key)
        return ApiKeyRead.from_entity(key)

    async def delete(self, key_id: uuid.UUID) -> None:
        key = await self._keys.get(key_id)
        if key is None:
            return
        await self._keys.delete(key)
        self._invalidate(key_id, "deleted")
        await self._uow.commit()
