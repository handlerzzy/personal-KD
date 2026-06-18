from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Zhipu Embedding
    zhipu_api_key: str = ""
    # LLM (mimo-2.5)
    llm_api_base: str = ""  # must be set in .env (e.g. https://api.openai.com/v1)
    llm_api_key: str = ""
    llm_model: str = "mimo-v2.5"
    # DashScope (qwen-flash for fast classification)
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-flash"
    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    # Reranker
    reranker_model_path: str = "./models/jina-reranker-v3"
    # Data
    data_dir: str = "./data"
    # Embedding
    embedding_model: str = "embedding-3"
    embedding_dimensions: int = 512
    # JWT Authentication - MUST be set in .env for production
    secret_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    def model_post_init(self, __context) -> None:
        """Validate settings after initialization."""
        if not self.secret_key:
            import os

            # Allow random key only in development (DEVELOPMENT=true in .env)
            if os.environ.get("DEVELOPMENT", "").lower() == "true":
                import warnings

                warnings.warn(
                    "SECRET_KEY is not set! Using a random key for this session. "
                    "Set SECRET_KEY in .env for production to ensure token persistence.",
                    UserWarning,
                    stacklevel=2,
                )
                import secrets

                self.secret_key = secrets.token_hex(32)
            else:
                raise RuntimeError(
                    "SECRET_KEY is not set! "
                    "Set SECRET_KEY in .env for production deployment. "
                    "Example: SECRET_KEY=your-secret-key-here"
                )


settings = Settings()
DATA_DIR = Path(settings.data_dir)
KB_DIR = DATA_DIR / "knowledge_bases"
UPLOAD_DIR = DATA_DIR / "uploads"
BM25_DIR = DATA_DIR / "bm25_indexes"

# Ensure dirs exist
for d in [DATA_DIR, KB_DIR, UPLOAD_DIR, BM25_DIR]:
    d.mkdir(parents=True, exist_ok=True)
