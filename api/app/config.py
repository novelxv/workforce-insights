from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://localhost/insights"
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_ttl_minutes: int = 8 * 60
    cookie_secure: bool = False
    environment: str = "development"
    demo_mode: bool = True
    demo_password: str = "arunika-demo"

    # Optional: Gemini turns free-text questions into query specs. Without a key, a
    # rules-based parser handles the common phrasings.
    gemini_api_key: str = ""
    llm_model: str = "gemini-3.5-flash"
    llm_timeout_seconds: float = 20.0

    # Groups smaller than this are suppressed in every aggregate the API returns.
    min_group_size: int = 5

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
