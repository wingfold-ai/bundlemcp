from pydantic import BaseModel


class Page[T](BaseModel):
    """Pagination envelope."""

    items: list[T]
    total: int
    offset: int
    limit: int
