from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SYSU_JWXT_",
        env_file=".env",
        extra="ignore",
    )

    base_url: str = "https://jwxt.sysu.edu.cn/jwxt"
    browser_channel: str | None = None
    browser_headless: bool = True
    host: str = "127.0.0.1"
    port: int = 8000
    state_dir: Path = Path("data/state")
    cache_dir: Path = Path("data/cache")
    timeout_seconds: float = 20.0
    keepalive_interval_seconds: int = 300
    keepalive_jitter_seconds: int = 20
    qr_login_session_ttl_seconds: int = 240


settings = Settings()
