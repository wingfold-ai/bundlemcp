from typing import Any

from pydantic import BaseModel


class ConfigValue(BaseModel):
    value: Any
