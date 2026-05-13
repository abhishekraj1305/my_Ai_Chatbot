"""Build or rebuild the ChromaDB vector store from local portfolio documents."""

from __future__ import annotations

import uuid
from typing import List

import chromadb

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        RecursiveCharacterTextSplitter = None

from config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DATA_DIR,
    EMBEDDING_MODEL,
    VECTOR_DB_DIR,
)
from document_loader import LoadedDocument, load_documents
from utils.text_cleaner import clean_text


def _log(message: str) -> None:
    print(f"[ingest] {message}")


def load_embedding_model():
    """Load embeddings from cache first, then allow download if needed."""
    from sentence_transformers import SentenceTransformer

    try:
        return SentenceTransformer(EMBEDDING_MODEL, local_files_only=True)
    except Exception as local_exc:
        _log(f"Cached embedding model unavailable: {local_exc}")
        return SentenceTransformer(EMBEDDING_MODEL)


def create_chunks(documents: List[LoadedDocument]) -> List[dict]:
    splitter = None
    if RecursiveCharacterTextSplitter is not None:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    chunks: List[dict] = []
    for doc_index, document in enumerate(documents):
        cleaned = clean_text(document.text)
        if not cleaned:
            continue

        split_texts = (
            splitter.split_text(cleaned)
            if splitter is not None
            else _fallback_split_text(cleaned)
        )
        for chunk_index, chunk_text in enumerate(split_texts):
            chunk_id = f"{doc_index}-{chunk_index}-{uuid.uuid4().hex[:12]}"
            metadata = dict(document.metadata)
            metadata["chunk_index"] = chunk_index
            metadata["chunk_id"] = chunk_id
            chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "metadata": metadata,
                }
            )

    return chunks


def _fallback_split_text(text: str) -> List[str]:
    """Simple character chunker used only when LangChain splitters are missing."""
    chunks = []
    start = 0
    text_length = len(text)
    while start < text_length:
        end = min(start + CHUNK_SIZE, text_length)
        chunks.append(text[start:end].strip())
        if end == text_length:
            break
        start = max(end - CHUNK_OVERLAP, start + 1)
    return [chunk for chunk in chunks if chunk]


def rebuild_vector_db() -> int:
    _log(f"Loading documents from: {DATA_DIR}")
    documents = load_documents(DATA_DIR)
    if not documents:
        _log("No documents loaded. Vector DB was not rebuilt.")
        return 0

    chunks = create_chunks(documents)
    _log(f"Total files/records loaded: {len(documents)}")
    _log(f"Total chunks created: {len(chunks)}")

    if not chunks:
        _log("No chunks created. Check whether the documents contain readable text.")
        return 0

    try:
        model = load_embedding_model()
    except Exception as exc:
        _log(f"Embedding model loading failed: {exc}")
        raise

    client = chromadb.PersistentClient(path=VECTOR_DB_DIR)
    try:
        client.delete_collection(COLLECTION_NAME)
        _log(f"Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        _log("No existing collection found; creating a fresh one.")

    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "Abhishek portfolio document chunks"},
    )

    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=True).tolist()

    collection.add(
        ids=[chunk["id"] for chunk in chunks],
        documents=texts,
        embeddings=embeddings,
        metadatas=[chunk["metadata"] for chunk in chunks],
    )

    stored = collection.count()
    _log(f"Total chunks stored in ChromaDB: {stored}")
    _log("Success: Abhishek portfolio vector database is ready.")
    return stored


if __name__ == "__main__":
    rebuild_vector_db()
