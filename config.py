"""Central configuration for the portfolio chatbot.

Values are intentionally relative-path and environment-variable based so the
project runs locally, on GitHub, and on Hugging Face Spaces without secrets in
source control.
"""

import os

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


if load_dotenv:
    load_dotenv()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR", os.path.join(BASE_DIR, "vector_db"))

COLLECTION_NAME = os.getenv("COLLECTION_NAME", "abhishek_portfolio_docs")
EMBEDDING_MODEL = os.getenv(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
TOP_K = int(os.getenv("TOP_K", "4"))

# Optional. If HF_TOKEN is present, rag_chain.py can call a Hugging Face model.
# Llama models may require accepting the model license on Hugging Face first.
HF_TOKEN = os.getenv("HF_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")

# Optional local text generation. Disabled by default because small CPU models
# are often weaker than retrieval fallback and may need a separate download.
ENABLE_LOCAL_LLM = os.getenv("ENABLE_LOCAL_LLM", "0") == "1"
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "distilgpt2")
