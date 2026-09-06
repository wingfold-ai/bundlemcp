"""Offset/limit pagination provider for the management API."""

from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel, Field


class Pagination(BaseModel):
    """Offset/limit pagination: default 50, max 500; stable ordering is each service's job."""

    offset: Annotated[int, Query()] = Field(default=0, ge=0, description="Records to skip")
    limit: Annotated[int, Query()] = Field(
        default=50, ge=1, le=500, description="Maximum records in the page"
    )


PageProvider = Annotated[Pagination, Depends(Pagination)]
