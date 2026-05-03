"""Text cleanup helpers for modern RAG pipelines."""

import re
import unicodedata


def clean_text(text: str) -> str:
    """Normalize extracted document text without old NLP preprocessing.

    We keep punctuation and natural language intact because semantic embedding
    models benefit from readable context.
    """
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\x00", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Fix common extraction artifacts while preserving sentence punctuation.
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[^\S\n]+", " ", text)

    return text.strip()

