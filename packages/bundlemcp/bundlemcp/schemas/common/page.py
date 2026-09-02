from pydantic import BaseModel, Field


class Page[T](BaseModel):
    """Pagination envelope."""

    items: list[T] = Field(description="The page of results")
    total: int = Field(description="Total matching records, ignoring offset and limit")
    offset: int = Field(description="Records skipped before this page")
    limit: int = Field(description="Maximum records this page may contain")
