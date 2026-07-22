from pydantic import BaseModel


class BundleServerUpdate(BaseModel):
    enabled: bool = True
