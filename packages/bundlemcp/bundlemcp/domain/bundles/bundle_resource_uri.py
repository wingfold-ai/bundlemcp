"""How a bundle's own resources are addressed by URI."""

# no bundle name in the URI, so renaming the bundle does not change it
BUNDLE_RESOURCE_URI_PREFIX = "bundle://resources/"


def bundle_resource_uri(name: str) -> str:
    """The URI a bundle resource is presented under."""
    return f"{BUNDLE_RESOURCE_URI_PREFIX}{name}"


def is_bundle_uri(uri: str) -> bool:
    """Whether a URI is in the scheme the bundle itself answers, whatever follows it."""
    return uri.startswith("bundle:")


def bundle_resource_name(uri: str) -> str | None:
    """The resource name a bundle URI addresses, or None when it addresses none."""
    if not uri.startswith(BUNDLE_RESOURCE_URI_PREFIX):
        return None
    return uri.removeprefix(BUNDLE_RESOURCE_URI_PREFIX) or None
