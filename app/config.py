from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = "ollama"
    openai_chat_model: str = "qwen2.5:1.5b"
    openai_embedding_model: str = "nomic-embed-text"
    embedding_dimension: int = Field(default=768, gt=0)
    openai_base_url: str = "http://localhost:11434/v1"
    qdrant_collection: str = "document_chunks_nomic_embed_text_768"
    qdrant_url: str = "http://localhost:6333"
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "sqlite:///./app.db"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
