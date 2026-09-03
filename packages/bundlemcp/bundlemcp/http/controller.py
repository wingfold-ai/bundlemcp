"""One HTTP surface as an object: its routes, its prefix, and the policy they share."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from fastapi import APIRouter, FastAPI, params


class Controller(ABC):
    """A group of related routes declared as methods of one class.

    A subclass names its ``prefix`` and ``tags``, implements ``register`` by
    calling the verb helpers with its bound handler methods, and is mounted on
    the app by the composition root. Anything every route of the surface needs
    (authentication, a common dependency) is declared once through
    ``dependencies`` instead of repeated per route.
    """

    prefix: ClassVar[str] = ""
    tags: ClassVar[Sequence[str]] = ()
    include_in_schema: ClassVar[bool] = True

    def __init__(self, *, dependencies: Sequence[params.Depends] = ()) -> None:
        self.router = APIRouter(
            prefix=self.prefix, tags=list(self.tags), dependencies=list(dependencies)
        )
        self.register()

    @abstractmethod
    def register(self) -> None:
        """Declare every route of this surface."""

    def mount(self, app: FastAPI, *, prefix: str = "") -> None:
        app.include_router(self.router, prefix=prefix)

    def route(self, method: str, path: str, handler: Callable[..., Any], **options: Any) -> None:
        options.setdefault("include_in_schema", self.include_in_schema)
        self.router.add_api_route(path, handler, methods=[method], **options)

    def get(self, path: str, handler: Callable[..., Any], **options: Any) -> None:
        self.route("GET", path, handler, **options)

    def post(self, path: str, handler: Callable[..., Any], **options: Any) -> None:
        self.route("POST", path, handler, **options)

    def put(self, path: str, handler: Callable[..., Any], **options: Any) -> None:
        self.route("PUT", path, handler, **options)

    def delete(self, path: str, handler: Callable[..., Any], **options: Any) -> None:
        self.route("DELETE", path, handler, **options)
