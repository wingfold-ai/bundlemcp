import uuid
from datetime import datetime

from pydantic import Field

from bundlemcp.domain.bundles.bundle_content_rejected import BundleContentRejected
from bundlemcp.domain.bundles.prompt_listing import PromptListing
from bundlemcp.domain.bundles.prompt_message import PromptMessage
from bundlemcp.domain.bundles.prompt_template import substitute
from bundlemcp.domain.shared.clock import utcnow


class BundlePrompt(PromptListing):
    """A message template authored on a bundle and served by the gateway itself.

    Its text may refer to the prompt's arguments as ``{{name}}``; rendering
    replaces each with the supplied value, or with nothing for an optional
    argument left out. A message may instead name one of the bundle's
    resources, which the gateway embeds when the prompt is rendered.
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Identifier of the prompt")
    bundle_id: uuid.UUID = Field(description="Bundle the prompt belongs to")
    messages: list[PromptMessage] = Field(  # BPR-1
        min_length=1, description="Messages of the prompt, in conversation order"
    )
    created_at: datetime = Field(default_factory=utcnow, description="When it was created")
    updated_at: datetime = Field(default_factory=utcnow, description="When it last changed")

    @property
    def text_bytes(self) -> int:
        """Size of all message text, in UTF-8 bytes."""
        return sum(len(m.text.encode()) for m in self.messages if m.text is not None)

    @property
    def resource_names(self) -> set[str]:
        """Names of the bundle resources the messages embed."""
        return {m.resource for m in self.messages if m.resource is not None}

    def check_references(self, bundle_resources: set[str]) -> None:
        """Refuse placeholders for undeclared arguments and embeds of unknown resources."""
        # BPR-3
        declared = {argument.name for argument in self.arguments}
        used = set().union(*(message.placeholders for message in self.messages))
        if undeclared := sorted(used - declared):
            raise BundleContentRejected(
                f"placeholders name undeclared arguments: {', '.join(undeclared)}"
            )
        if unknown := sorted(self.resource_names - bundle_resources):
            raise BundleContentRejected(
                f"messages embed resources this bundle does not have: {', '.join(unknown)}"
            )

    def render(self, supplied: dict[str, str]) -> list[PromptMessage]:
        """The messages with every placeholder replaced; resource messages are unchanged."""
        # BPR-3, BPR-4
        return [
            message.model_copy(update={"text": substitute(message.text, supplied)})
            if message.text is not None
            else message
            for message in self.messages
        ]
