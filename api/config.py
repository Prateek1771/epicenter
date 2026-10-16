"""Settings from the environment (LLD §11). The only module that reads env vars."""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _value(v) -> bool:
    """Docker Compose's env_file keeps an inline comment when the value before it is empty (`KEY=   # note` arrives
    as `# note`), so a value that starts with `#` counts as unset."""
    return bool(v) and not (isinstance(v, str) and v.strip().startswith("#"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    falkordb_url: str = "redis://:pw@falkordb:6379"
    falkordb_mcp_url: str | None = None
    mcp_api_key: str | None = None

    openrouter_api_key: str | None = None
    openrouter_url: str = "https://openrouter.ai/api"
    llm_model: str = "openai/gpt-4o-2024-11-20"  # pinned snapshot: same prompt, same model, reproducible output
    jev_model: str = "typesafe/jev-1.13"

    openconnector_url: str | None = None
    openconnector_api_key: str | None = None
    slack_channel: str | None = None  # Slack channel id for POST /deliver
    linear_team_id: str | None = None

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

    @field_validator("llm_model", "jev_model", mode="before")
    @classmethod
    def _blank_is_default(cls, v, info):
        # `LLM_MODEL=` in .env means "use the pinned default", not an empty model id
        return v if _value(v) else cls.model_fields[info.field_name].default

    @field_validator("openrouter_api_key", "openconnector_api_key", "api_key", "slack_channel", "linear_team_id",
                     mode="before")  # fmt: skip
    @classmethod
    def _blank_is_none(cls, v):
        return v if _value(v) else None


@lru_cache
def get_settings() -> Settings:
    return Settings()
