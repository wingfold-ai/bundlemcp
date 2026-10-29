"""Rendering a logged exception as a traceback that carries no value the code was handling."""

import sys
import traceback
from collections.abc import MutableMapping
from typing import Any

from pydantic import ValidationError

CAUSE_SEPARATOR = "\nThe above exception was the direct cause of the following exception:\n\n"
CONTEXT_SEPARATOR = "\nDuring handling of the above exception, another exception occurred:\n\n"


class TracebackRenderer:
    """A structlog processor that turns an event's ``exc_info`` into an ``exception`` string.

    The string reads like the standard library's traceback: the chain of causes and contexts,
    each with its stack frames and its type and message, and the members of an exception
    group indented beneath it. It never holds a frame's local variables, and a Pydantic
    validation error is rendered from its error list without the input it rejected, because
    either can hold a token or a decrypted secret.
    """

    def __call__(
        self, logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        exception = self._exception(event_dict.pop("exc_info", None))
        if exception is not None:
            event_dict["exception"] = "".join(self._render(exception, set())).rstrip("\n")
        return event_dict

    @staticmethod
    def _exception(exc_info: object) -> BaseException | None:
        """The exception an ``exc_info`` value names: ``True`` means the one being handled."""
        if exc_info is True:
            return sys.exc_info()[1]
        if isinstance(exc_info, BaseException):
            return exc_info
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            value = exc_info[1]
            return value if isinstance(value, BaseException) else None
        return None

    def _render(self, exception: BaseException, seen: set[int]) -> list[str]:
        seen.add(id(exception))
        lines: list[str] = []
        cause, context = exception.__cause__, exception.__context__
        if cause is not None and id(cause) not in seen:
            lines += [*self._render(cause, seen), CAUSE_SEPARATOR]
        elif context is not None and not exception.__suppress_context__ and id(context) not in seen:
            lines += [*self._render(context, seen), CONTEXT_SEPARATOR]
        if exception.__traceback__ is not None:
            lines.append("Traceback (most recent call last):\n")
            frames = traceback.StackSummary.extract(
                traceback.walk_tb(exception.__traceback__), capture_locals=False
            )
            lines += frames.format()
        lines += self._message(exception)
        if isinstance(exception, BaseExceptionGroup):
            for number, member in enumerate(exception.exceptions, start=1):
                lines.append(f"+---------------- {number} ----------------\n")
                member_text = "".join(self._render(member, seen))
                lines += [f"| {line}" for line in member_text.splitlines(keepends=True)]
        return lines

    @staticmethod
    def _message(exception: BaseException) -> list[str]:
        """The exception's type and message; a validation error's lists locations, not input."""
        if not isinstance(exception, ValidationError):
            return traceback.format_exception_only(type(exception), exception)
        name = f"{type(exception).__module__}.{type(exception).__qualname__}"
        count = exception.error_count()
        plural = "" if count == 1 else "s"
        lines = [f"{name}: {count} validation error{plural} for {exception.title}\n"]
        for error in exception.errors(include_input=False, include_url=False):
            location = ".".join(str(part) for part in error["loc"]) or "(root)"
            lines.append(f"  {location}: {error['msg']} ({error['type']})\n")
        return lines
