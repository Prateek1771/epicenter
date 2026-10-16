"""Settings from the environment (LLD §11). The only module that reads env vars."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    falkordb_url: str = "redis://:pw@falkordb:6379"
    falkordb_mcp_url: str | None = None
    mcp_api_key: str | None = None

    openrouter_api_key: str | None = None
    llm_model: str | None = None
    jev_model: str = "typesafe/jev-1.13"

    openconnector_url: str | None = None
    openconnector_api_key: str | None = None

    env_name: str = "astronomy-shop"
    web_origin: str = "http://localhost:3001"
    api_key: str | None = None  # deployed mode: X-API-Key required on /api/v1 (API.md)

    jaeger_url: str = "http://host.docker.internal:16686"
    prometheus_url: str = "http://host.docker.internal:9090"
    opensearch_url: str = "http://host.docker.internal:9200"

    flip_otel_file: str | None = None
    flip_log_dir: str | None = None
    flip_nginx_log: str | None = None

    rcaeval_dir: str = "./data/rcaeval"
    baseline_s: int = 480
    window_after_s: int = 300
    slow_burn_lookback_s: int = 21600
    slow_burn_kinds: str = "mem,saturation,cpu"

    query_timeout_s: float = 5.0  # LLD §10: per FalkorDB query
    weights_path: str = "weights.json"
    checkpoint_db: str = "./data/checkpoints.db"  # LangGraph checkpointer (resume after a crash)


@lru_cache
def get_settings() -> Settings:
    return Settings()
