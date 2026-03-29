from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = Field(..., description="Anthropic API key")

    # Web Search
    tavily_api_key: str = Field(..., description="Tavily search API key")

    # Financial Data
    alpha_vantage_api_key: str = Field("", description="Alpha Vantage API key")

    # Database
    database_url: str = Field("sqlite:///./research_agent.db")

    # RAG
    chroma_db_path: str = Field("./chroma_db")

    # Research depth
    standard_research_depth: int = Field(10)
    deep_research_depth: int = Field(20)
    max_search_results: int = Field(5)

    # API server
    host: str = Field("0.0.0.0")
    port: int = Field(8000)


# Single shared instance imported everywhere
settings = Settings()
