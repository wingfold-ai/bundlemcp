"""Caller identity routes: what the web app needs for any signed-in person, admin or
not — who they are, which endpoints they can connect a client to, and the clients
they have consented to.
"""

import uuid

from fastapi import HTTPException, Request, status

from bundlemcp.api.http.controller import Controller
from bundlemcp.api.http.management_auth import require_same_site_origin
from bundlemcp.api.http.providers import SettingsProvider
from bundlemcp.api.http.route import route
from bundlemcp.api.http.service_providers import (
    BundlePromptServiceProvider,
    BundleResourceServiceProvider,
    BundleServiceProvider,
    CallerResolverProvider,
    EndpointServiceProvider,
    UserServiceProvider,
)
from bundlemcp.api.oauth.session_cookie import SESSION_COOKIE
from bundlemcp.application.schemas import (
    AvailableEndpointRead,
    CataloguePromptRead,
    CatalogueResourceRead,
    CatalogueToolRead,
    ConsentRead,
    MeRead,
)
from bundlemcp.domain.access.api_key import ApiKey
from bundlemcp.domain.access.user import User


class MeController(Controller):
    prefix = "/me"
    tags = ("me",)

    @staticmethod
    async def _caller(request: Request, callers) -> User | ApiKey:
        caller = await callers.resolve(
            session_id=request.cookies.get(SESSION_COOKIE),
            authorization=request.headers.get("authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        match caller:
            case User():
                return caller
            case ApiKey() if caller.is_service_key:
                return caller
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not signed in")

    @classmethod
    async def _signed_in_user(cls, request: Request, callers) -> User:
        """The person behind a browser session; a service key has no consents of its own."""
        caller = await cls._caller(request, callers)
        if not isinstance(caller, User):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign in as a person")
        return caller

    @route.get("/consents")
    async def my_consents(
        self, request: Request, callers: CallerResolverProvider, users: UserServiceProvider
    ) -> list[ConsentRead]:
        """The clients the signed-in person has authorised, one entry per client and endpoint."""
        user = await self._signed_in_user(request, callers)
        return await users.list_consents(user.id)

    @route.delete("/consents/{consent_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def revoke_my_consent(
        self,
        consent_id: uuid.UUID,
        request: Request,
        callers: CallerResolverProvider,
        users: UserServiceProvider,
        settings: SettingsProvider,
    ) -> None:
        """Withdraw one of the signed-in person's consents, and the tokens issued under it."""
        user = await self._signed_in_user(request, callers)
        require_same_site_origin(request, settings)
        await users.revoke_own_consent(user.id, consent_id)

    @route.get("")
    async def whoami(self, request: Request, callers: CallerResolverProvider) -> MeRead:
        caller = await self._caller(request, callers)
        if isinstance(caller, User):
            return MeRead(
                kind="admin" if caller.is_admin else "user",
                user_id=caller.id,
                email=caller.email,
                display_name=caller.display_name,
                is_admin=caller.is_admin,
            )
        return MeRead(kind="service", api_key_id=caller.id)

    @route.get("/endpoints")
    async def available_endpoints(
        self,
        request: Request,
        callers: CallerResolverProvider,
        endpoints: EndpointServiceProvider,
        settings: SettingsProvider,
    ) -> list[AvailableEndpointRead]:
        """The catalogue for any signed-in person: enabled endpoints that accept OAuth."""
        await self._caller(request, callers)
        return await endpoints.available(settings.public_base)

    @route.get("/bundles/{bundle_name}/tools")
    async def bundle_tools(
        self,
        bundle_name: str,
        request: Request,
        callers: CallerResolverProvider,
        endpoints: EndpointServiceProvider,
        bundles: BundleServiceProvider,
    ) -> list[CatalogueToolRead]:
        """The tools a bundle serves, for a signed-in person reading its catalogue entry."""
        await self._caller(request, callers)
        # The bundle is readable only through an endpoint that would accept this
        # caller, so the reachability check comes before any bundle content.
        bundle_id = await endpoints.reachable_bundle_id(bundle_name)
        return await bundles.catalogue_tools(bundle_id)

    @route.get("/bundles/{bundle_name}/prompts")
    async def bundle_prompts(
        self,
        bundle_name: str,
        request: Request,
        callers: CallerResolverProvider,
        endpoints: EndpointServiceProvider,
        prompts: BundlePromptServiceProvider,
    ) -> list[CataloguePromptRead]:
        """The prompts a bundle itself offers, for a signed-in person reading its catalogue
        entry."""
        await self._caller(request, callers)
        bundle_id = await endpoints.reachable_bundle_id(bundle_name)
        return await prompts.catalogue(bundle_id)

    @route.get("/bundles/{bundle_name}/resources")
    async def bundle_resources(
        self,
        bundle_name: str,
        request: Request,
        callers: CallerResolverProvider,
        endpoints: EndpointServiceProvider,
        resources: BundleResourceServiceProvider,
    ) -> list[CatalogueResourceRead]:
        """The documents a bundle itself offers, for a signed-in person reading its catalogue
        entry."""
        await self._caller(request, callers)
        bundle_id = await endpoints.reachable_bundle_id(bundle_name)
        return await resources.catalogue(bundle_id)
