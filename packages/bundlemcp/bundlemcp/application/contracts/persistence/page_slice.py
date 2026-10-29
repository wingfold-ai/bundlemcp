from pydantic import BaseModel, Field


class PageSlice[T](BaseModel):
    """One page of entities cut from a query, and the size of the whole result."""

    items: list[T] = Field(description="The entities on this page, in the query's order")
    total: int = Field(ge=0, description="How many entities the query matched before paging")
