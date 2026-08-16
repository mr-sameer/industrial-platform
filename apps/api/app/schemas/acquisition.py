"""Pydantic schemas — Module 5B (Industrial Data Acquisition Foundation)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.acquisition_job import AcquisitionJobStatus
from app.models.acquisition_job_event import AcquisitionEventOutcome


class AcquisitionJobCreate(BaseModel):
    source_id: uuid.UUID
    collector_type: str = Field(min_length=1, max_length=64)
    requested_scope: dict[str, object] = Field(default_factory=dict)


class AcquisitionJobPublic(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    collector_type: str
    status: AcquisitionJobStatus
    requested_scope: dict[str, object] | None
    result_count: int
    skipped_count: int
    failed_count: int
    retry_count: int
    error_message: str | None
    created_by: uuid.UUID | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AcquisitionJobPage(BaseModel):
    items: list[AcquisitionJobPublic]
    total: int
    page: int
    page_size: int
    total_pages: int


class AcquisitionJobEventPublic(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    outcome: AcquisitionEventOutcome
    external_identifier: str | None
    raw_observation_id: uuid.UUID | None
    error_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AcquisitionJobEventPage(BaseModel):
    items: list[AcquisitionJobEventPublic]
    total: int
    page: int
    page_size: int
    total_pages: int
