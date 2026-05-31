from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Zhipu Embedding
    zhipu_api_key: str = ""
    # LLM (mimo-v2.5)
    llm_api_base: str = "https://api.example.com/v1"
    llm_api_key: str = ""
    llm_model: str = "mimo-v2.5"
    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    # Reranker
    reranker_model_path: str = "./models/jina-reranker-v3"
    # Data
    data_dir: str = "./data"
    # Embedding
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 512

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
DATA_DIR = Path(settings.data_dir)
KB_DIR = DATA_DIR / "knowledge_bases"
UPLOAD_DIR = DATA_DIR / "uploads"
BM25_DIR = DATA_DIR / "bm25_indexes"

# Ensure dirs exist
for d in [DATA_DIR, KB_DIR, UPLOAD_DIR, BM25_DIR]:
    d.mkdir(parents=True, exist_ok=True)
