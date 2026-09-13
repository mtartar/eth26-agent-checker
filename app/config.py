"""Centralized configuration.

Why this file exists: in a small script it's tempting to call
`os.environ["SOME_KEY"]` wherever you need it. In a production system that
becomes a debugging nightmare — you can't tell what configuration the app
even needs without grepping the whole codebase, and there's no single place
to validate that required values are present and well-typed.

`pydantic-settings` solves this: define every setting once, with a type and
a default, and the rest of the app imports `get_settings()` instead of ever
touching `os.environ` directly. This also makes tests trivial — you can
construct a `Settings` object directly with whatever values a test needs,
without touching real environment variables at all.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every configuration value the app needs, loaded from the environment or `.env`."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "fixture" runs entirely offline against recorded responses in
    # tests/fixtures/. "live" makes real calls to external APIs. Always
    # build and test against "fixture" first — see PLAN.md.
    data_source: Literal["fixture", "live"] = "fixture"

    database_url: str = "sqlite:///./agent_checker.db"

    # Empty string means "use the in-memory cache" — see app/cache.py.
    redis_url: str = ""

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"

    the_graph_api_key: str = ""
    the_graph_gateway_url: str = "https://gateway.thegraph.com"

    grc20_api_origin: str = ""
    grc20_space_id: str = ""

    log_level: str = "INFO"

    @property
    def is_live(self) -> bool:
        """Whether the app should call real external APIs instead of fixtures."""
        return self.data_source == "live"


@lru_cache
def get_settings() -> Settings:
    """Cached so we parse the environment once per process, not once per call."""
    return Settings()
