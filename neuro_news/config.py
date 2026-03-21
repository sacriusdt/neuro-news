from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field
from platformdirs import user_config_path, user_data_path
from dotenv import dotenv_values

from .utils import model_dump, model_validate

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-sonnet-20240620",
    "openrouter": "anthropic/claude-3.5-sonnet",
}


class AppConfig(BaseModel):
    db_path: str
    poll_interval_minutes: int = 5
    provider: str = "openrouter"
    model: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    openrouter_api_key: str | None = None
    max_results: int = 20
    timeout_seconds: int = 20
    max_concurrency: int = 8


class ConfigStore:
    def __init__(self) -> None:
        self.config_dir = Path(user_config_path("neuro-news", "neuro-news"))
        self.config_path = self.config_dir / "config.json"
        self.data_dir = Path(user_data_path("neuro-news", "neuro-news"))

    def default_config(self) -> AppConfig:
        db_path = str(self.data_dir / "neuro_news.db")
        return AppConfig(db_path=db_path)

    def load(self) -> AppConfig:
        if not self.config_path.exists():
            config = self.default_config()
            self.save(config)
            config = apply_dotenv_overrides(config)
            return apply_env_overrides(config)
        data = json.loads(self.config_path.read_text(encoding="utf-8"))
        config = model_validate(AppConfig, data)
        config = apply_dotenv_overrides(config)
        return apply_env_overrides(config)

    def save(self, config: AppConfig) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        payload = model_dump(config)
        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def apply_env_overrides(config: AppConfig) -> AppConfig:
    db_path = os.getenv("NEURO_NEWS_DB_PATH")
    provider = os.getenv("NEURO_NEWS_PROVIDER")
    model = os.getenv("NEURO_NEWS_MODEL")
    poll_interval = os.getenv("NEURO_NEWS_POLL_INTERVAL")
    max_results = os.getenv("NEURO_NEWS_MAX_RESULTS")
    timeout = os.getenv("NEURO_NEWS_TIMEOUT")

    if db_path:
        config.db_path = db_path
    if provider:
        config.provider = provider
    if model:
        config.model = model
    if poll_interval:
        config.poll_interval_minutes = int(poll_interval)
    if max_results:
        config.max_results = int(max_results)
    if timeout:
        config.timeout_seconds = int(timeout)

    config.openai_api_key = os.getenv("OPENAI_API_KEY", config.openai_api_key)
    config.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", config.anthropic_api_key)
    config.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", config.openrouter_api_key)

    return config


def apply_dotenv_overrides(config: AppConfig) -> AppConfig:
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return config
    values = dotenv_values(env_path)

    model = values.get("NEURO_NEWS_MODEL")
    if model:
        config.model = str(model)

    provider = values.get("NEURO_NEWS_PROVIDER")
    if provider:
        config.provider = str(provider)

    openai_key = values.get("OPENAI_API_KEY")
    if openai_key:
        config.openai_api_key = str(openai_key)

    anthropic_key = values.get("ANTHROPIC_API_KEY")
    if anthropic_key:
        config.anthropic_api_key = str(anthropic_key)

    openrouter_key = values.get("OPENROUTER_API_KEY")
    if openrouter_key:
        config.openrouter_api_key = str(openrouter_key)

    return config


def get_model_for_provider(provider: str, config: AppConfig) -> str:
    if config.model:
        return config.model
    return DEFAULT_MODELS.get(provider, "gpt-4o-mini")
