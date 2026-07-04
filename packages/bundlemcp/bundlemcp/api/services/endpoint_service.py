"""Endpoint business logic: CRUD, auth-mode/profile rules, rate-limit config."""

from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from bundlemcp.api.services.errors import ConflictError, InvalidInputError, NotFoundError
from bundlemcp.api.validators import endpoint_violates_per_user_upstream
from bundlemcp.models import Bundle, Endpoint
from bundlemcp.schemas import EndpointRead, EndpointUpsert, Page
from bundlemcp.store.invalidation import InvalidationEvent, publish_invalidation


class EndpointService:
    def __init__(self, db: AsyncSession, redis: Redis) -> None:
        self._db = db
        self._redis = redis

    async def _by_name(self, name: str) -> Endpoint | None:
        return (
            await self._db.execute(select(Endpoint).where(Endpoint.name == name))
        ).scalar_one_or_none()

    async def _get(self, name: str) -> Endpoint:
        ep = await self._by_name(name)
        if ep is None:
            raise NotFoundError("endpoint not found")
        return ep

    async def _invalidate(self, name: str, action: str) -> None:
        await publish_invalidation(
            self._redis, InvalidationEvent(entity_type="endpoint", key=name, action=action)
        )

    async def list(self, *, offset: int, limit: int) -> Page[EndpointRead]:
        total = (await self._db.execute(select(func.count()).select_from(Endpoint))).scalar_one()
        rows = (
            await self._db.execute(
                select(Endpoint)
                .order_by(Endpoint.created_at, Endpoint.id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars()
        return Page(
            items=[EndpointRead.model_validate(e) for e in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    async def get(self, name: str) -> EndpointRead:
        return EndpointRead.model_validate(await self._get(name))

    async def upsert(self, body: EndpointUpsert) -> EndpointRead:
        bundle = (
            await self._db.execute(select(Bundle).where(Bundle.name == body.bundle_name))
        ).scalar_one_or_none()
        if bundle is None:
            raise NotFoundError("bundle not found")
        # UPO-6: a none-only endpoint can't expose a bundle with a per_user upstream
        if await endpoint_violates_per_user_upstream(
            self._db, bundle.id, [m.value for m in body.auth_modes]
        ):
            raise ConflictError(
                "a 'none'-auth endpoint cannot expose a bundle with a per_user upstream "
                "server (UPO-6)"
            )
        ep = await self._by_name(body.name)
        created = ep is None
        if ep is None:
            ep = Endpoint(name=body.name, bundle_id=bundle.id)
        ep.bundle_id = bundle.id
        ep.profile = body.profile
        ep.auth_modes = [m.value for m in body.auth_modes]
        ep.rate_limit = body.rate_limit.model_dump() if body.rate_limit else None
        ep.enabled = body.enabled
        self._db.add(ep)
        await self._db.commit()
        await self._db.refresh(ep)
        await self._invalidate(body.name, "created" if created else "updated")
        return EndpointRead.model_validate(ep)

    async def rename(self, name: str, new_name: str, *, force: bool) -> EndpointRead:
        """Renaming breaks every connected client's URL, so force is required."""
        if not force:
            raise ConflictError(
                "renaming an endpoint changes its public URL and breaks connected clients — "
                "retry with force=true (EP-8)"
            )
        ep = await self._get(name)
        try:
            # reuse DTO name validation (reserved names, slug)
            EndpointUpsert(name=new_name, bundle_name="x", allow_unauthenticated=True)
        except ValidationError as exc:
            raise InvalidInputError(str(exc)) from None
        ep.name = new_name
        await self._db.commit()
        await self._db.refresh(ep)
        await self._invalidate(new_name, "updated")
        return EndpointRead.model_validate(ep)

    async def delete(self, name: str) -> None:
        ep = await self._by_name(name)
        if ep is not None:
            await self._db.delete(ep)
            await self._db.commit()
            await self._invalidate(name, "deleted")
