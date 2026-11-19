from collections.abc import Callable

from pydantic import BaseModel, Field

from bundlemcp.application.contracts.persistence.page_slice import PageSlice


class Page[T](BaseModel):
    """Pagination envelope."""

    items: list[T] = Field(description="The page of results")
    total: int = Field(description="Total matching records, ignoring offset and limit")
    offset: int = Field(description="Records skipped before this page")
    limit: int = Field(description="Maximum records this page may contain")

    @classmethod
    def of[E](
        cls,
        page_slice: PageSlice[E],
        *,
        offset: int,
        limit: int,
        read: Callable[[E], T],
    ) -> Page[T]:
        """The page a repository query returned, each entity rendered through ``read``."""
        return cls(
            items=[read(entity) for entity in page_slice.items],
            total=page_slice.total,
            offset=offset,
            limit=limit,
        )
