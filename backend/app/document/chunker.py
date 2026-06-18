from __future__ import annotations

import re


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences based on punctuation."""
    # Split by sentence-ending punctuation, keeping the delimiter
    # We use positive lookbehind to keep the delimiter attached to the sentence
    # or split and re-add. Splitting is safer to avoid losing characters.

    # Delimiters: 。！？；.!?;
    # We want to split AFTER these characters.
    sentences = re.split(r"(?<=[。！？；.!?;])\s*", text)
    return [s.strip() for s in sentences if s.strip()]


def _get_heading(line: str) -> str | None:
    """Extract heading from a line if it starts with #."""
    match = re.match(r"^(#{1,3})\s+(.*)", line)
    if match:
        return match.group(0).strip()  # Return full heading "### Title"
    return None


def split_text(
    text: str, kb_id: str, doc_id: str, chunk_size: int = 1500, chunk_overlap: int = 200
) -> list[dict]:
    """Split text into chunks using heading-aware semantic splitting."""

    lines = text.split("\n")

    sections: list[dict] = []
    current_section_lines: list[str] = []
    current_heading: str | None = None

    # Level 1: Split by headings
    for line in lines:
        heading = _get_heading(line)
        if heading:
            # If we have content in the current section, save it
            if current_section_lines:
                sections.append(
                    {"heading": current_heading, "text": "\n".join(current_section_lines)}
                )
            current_section_lines = [line]  # Include heading in the section text
            current_heading = heading
        else:
            current_section_lines.append(line)

    # Add the last section
    if current_section_lines:
        sections.append({"heading": current_heading, "text": "\n".join(current_section_lines)})

    final_chunks: list[dict] = []
    chunk_index = 0

    for section in sections:
        section_text = section["text"].strip()
        heading = section["heading"]

        if not section_text:
            continue

        # Level 2: Split by paragraphs (\n\n)
        # We treat consecutive non-empty lines as paragraphs,
        # or explicit double newlines.
        paragraphs = re.split(r"\n\s*\n", section_text)

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # If paragraph fits in chunk size, keep it as one chunk
            # (Add chunk_size check)
            if len(para) <= chunk_size:
                final_chunks.append(
                    {
                        "chunk_id": f"{doc_id}_chunk_{chunk_index:04d}",
                        "text": para,
                        "metadata": {
                            "kb_id": kb_id,
                            "doc_id": doc_id,
                            "chunk_index": chunk_index,
                            "heading": heading,
                        },
                    }
                )
                chunk_index += 1
            else:
                # Level 3: Split by sentences
                sentences = _split_into_sentences(para)

                current_chunk_text = ""

                for sent in sentences:
                    # If adding this sentence exceeds limit
                    if len(current_chunk_text) + len(sent) > chunk_size:
                        if current_chunk_text:
                            final_chunks.append(
                                {
                                    "chunk_id": f"{doc_id}_chunk_{chunk_index:04d}",
                                    "text": current_chunk_text.strip(),
                                    "metadata": {
                                        "kb_id": kb_id,
                                        "doc_id": doc_id,
                                        "chunk_index": chunk_index,
                                        "heading": heading,
                                    },
                                }
                            )
                            chunk_index += 1

                            # Handle Overlap: take last N chars of previous chunk
                            # We prefer to start new chunk with overlap if it helps context
                            # But since we split by sentences, we might just carry over the sentence
                            # or take tail of previous chunk.
                            # Requirement: handle overlap by including
                            # the last N chars of the previous chunk

                            if chunk_overlap > 0 and len(current_chunk_text) > 0:
                                overlap_text = current_chunk_text[-chunk_overlap:]
                                # Avoid starting with partial words if possible,
                                # but strict requirement is "last N chars"
                                current_chunk_text = overlap_text + "\n" + sent
                            else:
                                current_chunk_text = sent
                        else:
                            # Sentence itself is longer than chunk_size?
                            # This shouldn't happen often with sentences, but just in case
                            # we force add it as its own chunk or split further (not requested).
                            current_chunk_text = sent
                    else:
                        current_chunk_text += ("\n" if current_chunk_text else "") + sent

                # Add remaining text
                if current_chunk_text.strip():
                    final_chunks.append(
                        {
                            "chunk_id": f"{doc_id}_chunk_{chunk_index:04d}",
                            "text": current_chunk_text.strip(),
                            "metadata": {
                                "kb_id": kb_id,
                                "doc_id": doc_id,
                                "chunk_index": chunk_index,
                                "heading": heading,
                            },
                        }
                    )
                    chunk_index += 1

    # If no headings were found (plain text), the above logic still works
    # (sections will have heading=None, text=full_content).
    # If no headings found (plain text), fall back to paragraph-based splitting.
    # This logic naturally handles it since it treats the whole text as one section.

    return final_chunks
