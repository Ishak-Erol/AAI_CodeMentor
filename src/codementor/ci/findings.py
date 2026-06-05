from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    file: str
    line: int = Field(ge=1)
    message: str
    severity: str
