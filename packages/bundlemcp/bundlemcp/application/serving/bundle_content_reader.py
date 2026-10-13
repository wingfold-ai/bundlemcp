"""Reading the bodies of a bundle's own prompts and resources while serving."""

import uuid

from bundlemcp.application.contracts.persistence.unit_of_work import UnitOfWorkFactory
from bundlemcp.application.serving.rendered_prompt import RenderedPrompt
from bundlemcp.domain.bundles.bundle_resource import BundleResource


class BundleContentReader:
    """Fetches what a bundle's view lists but does not carry.

    The view is rebuilt for every request, so it holds names and descriptions
    only; a prompt's messages and a resource's content are read here, by name,
    when a client asks for that one entry. No upstream is involved.
    """

    def __init__(self, units: UnitOfWorkFactory) -> None:
        self._units = units

    async def render_prompt(
        self, bundle_id: uuid.UUID, name: str, arguments: dict[str, str]
    ) -> RenderedPrompt | None:
        """The prompt rendered with these arguments, or None when the bundle has no such
        prompt."""
        # BPR-3, BPR-8
        async with self._units.open() as uow:
            prompt = await uow.bundle_prompts.find(bundle_id, name)
            if prompt is None:
                return None
            resources = {}
            for resource_name in sorted(prompt.resource_names):
                resource = await uow.bundle_resources.find(bundle_id, resource_name)
                if resource is not None:
                    resources[resource_name] = resource
        return RenderedPrompt(
            description=prompt.description,
            messages=prompt.render(arguments),
            resources=resources,
        )

    async def resource(self, bundle_id: uuid.UUID, name: str) -> BundleResource | None:
        """One resource with its content, or None when the bundle has no such resource."""
        async with self._units.open() as uow:
            return await uow.bundle_resources.find(bundle_id, name)
