"""Configuration settings for the Orchestrator Agent."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Orchestrator agent configuration from environment variables."""

    # LLM Configuration
    LLM_API_BASE: str = os.getenv("LLM_API_BASE", "http://localhost:11434/v1")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "dummy")
    TASK_MODEL_ID: str = os.getenv("TASK_MODEL_ID", "gpt-4o-mini")
    MODEL_TEMPERATURE: float = float(os.getenv("MODEL_TEMPERATURE", "0.0"))

    # Service Configuration
    SERVICE_PORT: int = int(os.getenv("PORT", "8000"))
    SERVICE_HOST: str = os.getenv("HOST", "0.0.0.0")

    # MCP Configuration (a2a-bridge)
    MCP_URL: str = os.getenv("MCP_URL", "")
    MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "http")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
