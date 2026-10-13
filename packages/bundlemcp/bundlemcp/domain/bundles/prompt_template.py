"""The ``{{argument}}`` placeholders a bundle prompt's text may carry."""

import re
from collections.abc import Mapping

# a placeholder is the argument name in double braces, nothing more.
PLACEHOLDER = re.compile(r"\{\{([a-zA-Z0-9_-]+)\}\}")


def placeholders(text: str) -> set[str]:
    """The argument names a text refers to."""
    return set(PLACEHOLDER.findall(text))


def substitute(text: str, values: Mapping[str, str]) -> str:
    """Replace each placeholder with its value, or with nothing when it has none.

    One pass over the original text: a substituted value is inserted verbatim
    and never scanned again, so a value that itself looks like a placeholder
    stays literal text.
    """
    return PLACEHOLDER.sub(lambda match: values.get(match.group(1), ""), text)
