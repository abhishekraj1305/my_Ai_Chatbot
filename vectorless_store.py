"""Fast vectorless document retrieval for the portfolio assistant.

This module keeps the hosted chatbot responsive by avoiding embedding model
downloads and Chroma startup work on the default path. It builds a small
in-memory BM25-style index from the local data folder.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Tuple

from config import CHUNK_OVERLAP, CHUNK_SIZE, DATA_DIR
from document_loader import load_documents
from utils.text_cleaner import clean_text


_records_cache: List[Dict] | None = None
_index_cache: Dict | None = None


TOKEN_RE = re.compile(r"[a-zA-Z0-9+#.]+")


STOP_WORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "can",
    "does",
    "for",
    "from",
    "has",
    "have",
    "his",
    "is",
    "me",
    "of",
    "on",
    "or",
    "raj",
    "tell",
    "the",
    "to",
    "what",
    "who",
    "with",
}


def _log(message: str) -> None:
    print(f"[vectorless_store] {message}")


def _tokenize(text: str) -> List[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    return [token for token in tokens if len(token) > 1 and token not in STOP_WORDS]


def _chunk_text(text: str) -> List[str]:
    text = clean_text(text)
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
            if boundary > start + int(CHUNK_SIZE * 0.55):
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return chunks


def collection_records() -> List[Dict]:
    global _records_cache
    if _records_cache is not None:
        return _records_cache

    records: List[Dict] = []
    for document in load_documents(DATA_DIR):
        for chunk_index, chunk in enumerate(_chunk_text(document.text)):
            metadata = dict(document.metadata)
            metadata["chunk_index"] = chunk_index
            records.append({"text": chunk, "metadata": metadata})

    _records_cache = records
    _log(f"Indexed {len(records)} vectorless chunks.")
    return records


def _build_index() -> Dict:
    global _index_cache
    if _index_cache is not None:
        return _index_cache

    records = collection_records()
    doc_terms = []
    doc_freq = Counter()
    total_length = 0

    for record in records:
        terms = Counter(_tokenize(record["text"]))
        doc_terms.append(terms)
        total_length += sum(terms.values())
        doc_freq.update(terms.keys())

    doc_count = max(len(records), 1)
    avg_length = total_length / doc_count if total_length else 1
    idf = {
        term: math.log(1 + (doc_count - freq + 0.5) / (freq + 0.5))
        for term, freq in doc_freq.items()
    }

    _index_cache = {
        "records": records,
        "doc_terms": doc_terms,
        "idf": idf,
        "avg_length": avg_length,
    }
    return _index_cache


def retrieve(question: str, top_k: int) -> Tuple[str, List[Dict]]:
    index = _build_index()
    records = index["records"]
    if not records:
        return "", []

    query_terms = _tokenize(question)
    if not query_terms:
        return "", []

    scores = []
    k1 = 1.4
    b = 0.72
    avg_length = index["avg_length"]
    idf = index["idf"]

    for record_index, terms in enumerate(index["doc_terms"]):
        doc_length = sum(terms.values()) or 1
        score = 0.0
        for term in query_terms:
            freq = terms.get(term, 0)
            if not freq:
                continue
            numerator = freq * (k1 + 1)
            denominator = freq + k1 * (1 - b + b * doc_length / avg_length)
            score += idf.get(term, 0.0) * numerator / denominator
        if score:
            scores.append((score, record_index))

    scores.sort(reverse=True)
    retrieved = []
    context_parts = []
    for score, record_index in scores[:top_k]:
        record = records[record_index]
        metadata = record["metadata"]
        source = metadata.get("file_name", "unknown source")
        page = metadata.get("page_number")
        source_label = f"{source}, page {page}" if page else source
        item = {
            "text": record["text"],
            "metadata": metadata,
            "distance": 1 / (score + 1),
        }
        retrieved.append(item)
        context_parts.append(f"Source: {source_label}\n{record['text']}")

    return "\n\n---\n\n".join(context_parts), retrieved


def list_sources() -> List[str]:
    sources = []
    for record in collection_records():
        source = record["metadata"].get("file_name")
        if source and source not in sources:
            sources.append(source)
    return sources
