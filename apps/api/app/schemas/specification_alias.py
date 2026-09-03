"""Pydantic schemas — SpecificationAlias management (the dedicated
ADMIN-only alias API; see app.api.v1.specification_alias's own
docstring for why this is a new, separate surface rather than a change
to the existing specification-creation endpoint)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SpecificationAliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=120)


class SpecificationAliasPublic(BaseModel):
    id: uuid.UUID
    specification_id: uuid.UUID
    alias: str
    created_at: datetime

    model_config = {"from_attributes": True}
