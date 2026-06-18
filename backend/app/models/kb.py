from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel


class KnowledgeBase(BaseModel):
    id: str = ""
    name: str
    description: str = ""
    created_at: str = ""
    doc_count: int = 0
    conv_count: int = 0

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
