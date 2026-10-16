from pydantic import BaseModel, ConfigDict, Field


class SecretRef(BaseModel):
    """A secret the document names instead of carrying, written ``{"$secret": "<NAME>"}``.

    An export puts one where a header value or a client secret would be. On import
    it means: keep the value the target already stores under that name.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True, frozen=True)

    name: str = Field(
        alias="$secret",
        min_length=1,
        description="What the withheld secret is: the header name, or 'client_secret'",
    )
