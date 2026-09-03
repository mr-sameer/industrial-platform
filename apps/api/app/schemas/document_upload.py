"""
Pydantic schema — generic document upload, Checkpoint 1 of the approved
Document -> Structured Product Data design review. See
app.api.v1.documents for the one route that produces this.
"""

from pydantic import BaseModel


class DocumentUploadPublic(BaseModel):
    storage_key: str
    sha256: str
    filename: str
    size_bytes: int
    content_type: str
