from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuration is read from the environment; nothing here has a production default.

    DATABASE_URL is required rather than defaulted so a misconfigured deploy fails at
    startup instead of quietly writing to a local database nobody is watching.
    """

    database_url: str = "postgresql+asyncpg://genesis:genesis@localhost:55432/findings"

    # Ingest limits. A scanner with a bad locator generator can emit one finding per DOM
    # node, so the payload is bounded and oversized batches are rejected rather than
    # truncated -- silently dropping half a report is worse than refusing it.
    max_findings_per_request: int = 500

    # Per-project write budget. In-process, so it holds for a single worker; the
    # multi-worker version belongs in Redis (see README, "Where Redis goes").
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    model_config = {"env_prefix": "FINDINGS_", "env_file": ".env"}


settings = Settings()
