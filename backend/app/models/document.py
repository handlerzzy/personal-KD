from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel


class Document(BaseModel):
    id: str = ""
    kb_id: str
    filename: str
    file_type: str  # pdf/txt/md
    file_size: int = 0
    chunk_count: int = 0
    created_at: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
