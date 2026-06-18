from __future__ import annotations
from pydantic import BaseModel
from datetime import UTC, datetime
from uuid import uuid4


class Conversation(BaseModel):
    id: str = ""
    kb_id: str
    title: str
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = uuid4().hex[:12]
        now = datetime.now(UTC).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now


class Message(BaseModel):
    id: str = ""
    conversation_id: str
    role: str  # user / assistant
    content: str = ""
    reasoning_content: str = ""
    sources: list[dict] = []
    created_at: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        if not self.id:
            self.id = uuid4().hex[:12]
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
