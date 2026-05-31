from __future__ import annotations

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    kb_id: str
    query: str
    retrieved_docs: list[dict]
    reasoning: str
    answer: str
