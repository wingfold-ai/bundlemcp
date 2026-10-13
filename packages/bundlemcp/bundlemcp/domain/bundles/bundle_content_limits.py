from pydantic import BaseModel, ConfigDict, Field

from bundlemcp.domain.bundles.bundle_content_rejected import BundleContentRejected
from bundlemcp.domain.bundles.bundle_prompt import BundlePrompt
from bundlemcp.domain.bundles.bundle_resource import BundleResource

KIB = 1024


class BundleContentLimits(BaseModel):
    """How much prompt and resource content one bundle may hold.

    Every limit is checked before a write and names itself when it refuses one;
    nothing is ever truncated to fit.
    """

    model_config = ConfigDict(frozen=True)

    max_prompts: int = Field(default=100, description="Prompts per bundle")
    max_resources: int = Field(default=200, description="Resources per bundle")
    max_prompt_text_bytes: int = Field(
        default=64 * KIB, description="Message text per prompt, in UTF-8 bytes"
    )
    max_resource_bytes: int = Field(
        default=256 * KIB, description="Content per resource, in UTF-8 bytes"
    )
    max_bundle_resource_bytes: int = Field(
        default=4 * KIB * KIB, description="Resource content per bundle, in UTF-8 bytes"
    )

    def check_prompt(self, prompt: BundlePrompt, *, prompts_after: int) -> None:
        """Refuse a prompt that is too large, or one more prompt than a bundle may hold."""
        if prompts_after > self.max_prompts:
            raise BundleContentRejected(f"a bundle holds at most {self.max_prompts} prompts")
        if prompt.text_bytes > self.max_prompt_text_bytes:
            raise BundleContentRejected(
                f"message text is {prompt.text_bytes} bytes; a prompt holds at most "
                f"{self.max_prompt_text_bytes // KIB} KiB"
            )

    def check_resource(
        self, resource: BundleResource, *, resources_after: int, bundle_bytes_after: int
    ) -> None:
        """Refuse a resource that is too large, or that takes its bundle over a limit."""
        if resources_after > self.max_resources:
            raise BundleContentRejected(f"a bundle holds at most {self.max_resources} resources")
        if resource.size_bytes > self.max_resource_bytes:
            raise BundleContentRejected(
                f"content is {resource.size_bytes} bytes; a resource holds at most "
                f"{self.max_resource_bytes // KIB} KiB"
            )
        if bundle_bytes_after > self.max_bundle_resource_bytes:
            raise BundleContentRejected(
                f"resources would total {bundle_bytes_after} bytes; a bundle holds at most "
                f"{self.max_bundle_resource_bytes // (KIB * KIB)} MiB of resource content"
            )


# The limits a bundle has unless a caller says otherwise; frozen, so safe to share.
DEFAULT_LIMITS = BundleContentLimits()
