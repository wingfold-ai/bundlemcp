"""Offset/limit pagination provider for the management API."""

from typing import Annotated

from fastapi import Depends, Query


class Pagination:
    """Offset/limit pagination: default 50, max 500, stable ordering handled per-router."""

    def __init__(
        self,
        offset: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> None:
        self.offset = offset
        self.limit = limit


PageProvider = Annotated[Pagination, Depends(Pagination)]
