from __future__ import annotations

from app.agent.state import AgentState
from app.document.chunker import split_text
from app.document.embedder import embed_texts
from app.document.parser import parse_document
from app.retrieval import dense, sparse


async def document_processing_node(state: AgentState) -> dict:
    """Process uploaded documents: parse, chunk, embed, index."""
    file_path = state.get("file_path", "")
    file_type = state.get("file_type", "")
    kb_id = state["kb_id"]
    doc_id = state.get("doc_id", "")

    if not file_path:
        return {"messages": []}

    # 1. Parse
    text = await parse_document(file_path, file_type)
    # 2. Chunk
    chunks = split_text(text, kb_id, doc_id)
    # 3. Embed
    texts = [c["text"] for c in chunks]
    embeddings = await embed_texts(texts)
    # 4. Index to Qdrant
    await dense.upsert_chunks(kb_id, chunks, embeddings)
    # 5. Index to BM25
    sparse.add_documents(kb_id, texts)

    return {
        "messages": [],
        "chunks": chunks,
        "chunk_count": len(chunks),
    }
