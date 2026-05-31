from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_text(text: str, kb_id: str, doc_id: str) -> list[dict]:
    """Split text into chunks using LangChain RecursiveCharacterTextSplitter."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
        length_function=len,
    )

    chunks = splitter.split_text(text)
    result = []
    for i, chunk_text in enumerate(chunks):
        chunk_text = chunk_text.strip()
        if not chunk_text:
            continue
        result.append({
            "chunk_id": f"{doc_id}_chunk_{i:04d}",
            "text": chunk_text,
            "metadata": {
                "kb_id": kb_id,
                "doc_id": doc_id,
                "chunk_index": i,
            }
        })
    return result
