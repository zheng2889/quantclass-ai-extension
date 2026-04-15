"""Configuration management for QuantClass backend."""

import os
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


class ProviderConfig(BaseModel):
    """LLM provider configuration."""
    name: str
    base_url: str
    api_key: str
    models: List[str] = Field(default_factory=list)
    # "openai" (default) or "anthropic" — determines which SDK class to use.
    # Most third-party proxies use the OpenAI-compatible protocol; only the
    # official Anthropic API (or proxies that mirror its native /v1/messages
    # schema) need "anthropic".
    protocol: str = Field(default="openai")


def _quantclass_home() -> Path:
    """Root directory for all QuantClass data, config, md files, etc.

    Priority:
      1. ``QUANTCLASS_HOME`` env var — used by tests to isolate from the
         real user directory (see ``tests/conftest.py``). CRITICAL: without
         this escape hatch, ``pytest tests/test_config.py::
         test_update_default_model`` used to overwrite the real user's
         ``~/.quantclass/config.yaml`` on every test run.
      2. ``~/.quantclass`` — default for all real deployments on macOS,
         Linux, and Windows (``Path.home()`` resolves correctly on all).
    """
    env = os.getenv("QUANTCLASS_HOME")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".quantclass"


def _default_data_dir() -> str:
    """Platform-aware default data directory."""
    return str(_quantclass_home() / "data")


class ConfigData(BaseModel):
    """Main configuration data structure."""
    host: str = "127.0.0.1"
    port: int = 8700
    data_dir: str = Field(default_factory=_default_data_dir)
    default_model: str = "claude-sonnet-4-6"
    default_provider: str = "anthropic"
    providers: Dict[str, ProviderConfig] = Field(default_factory=dict)
    
    model_config = ConfigDict(extra="allow")


def _generate_secret_key() -> str:
    """Generate a cryptographically secure secret key."""
    import secrets
    return secrets.token_urlsafe(32)


class Settings(BaseSettings):
    """FastAPI settings with config file integration."""
    # These can be overridden by environment variables
    host: str = "127.0.0.1"
    port: int = 8700
    debug: bool = False
    secret_key: str = Field(default_factory=_generate_secret_key)

    model_config = ConfigDict(env_prefix="QUANTCLASS_")


# Global config instance
_config: Optional[ConfigData] = None
_settings: Optional[Settings] = None


def get_config_path() -> Path:
    """Get the path to the config file."""
    return _quantclass_home() / "config.yaml"


def ensure_config_dir() -> Path:
    """Ensure config directory exists."""
    config_dir = _quantclass_home()
    config_dir.mkdir(parents=True, exist_ok=True)
    data_dir = config_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def create_default_config() -> ConfigData:
    """Create default configuration."""
    default_config = ConfigData(
        host="127.0.0.1",
        port=8700,
        data_dir=_default_data_dir(),
        default_model="claude-4.6-sonnet",
        default_provider="anthropic",
        providers={
            # All providers are user-configurable and require API keys.
            "openai": ProviderConfig(
                name="OpenAI",
                base_url="https://api.openai.com/v1",
                api_key=os.getenv("OPENAI_API_KEY", ""),
                models=["gpt-5", "gpt-5.1", "gpt-5.2", "gpt-5.3", "gpt-5.4", "o1-preview", "gpt-4o"]
            ),
            "anthropic": ProviderConfig(
                name="Anthropic",
                # We route Anthropic through the OpenAI-compatible endpoint
                # (/v1/chat/completions), so the base_url keeps /v1. Anthropic
                # officially supports this since 2024 and almost every third-
                # party Claude proxy implements the OpenAI schema.
                base_url="https://api.anthropic.com/v1",
                api_key=os.getenv("ANTHROPIC_API_KEY", ""),
                models=[
                    "claude-sonnet-4-6",
                    "claude-opus-4-6",
                    "claude-sonnet-4-6-thinking",
                    "claude-sonnet-4-5",
                    "claude-opus-4-5",
                    "claude-haiku-4-5",
                ]
            ),
            "gemini": ProviderConfig(
                name="Google Gemini",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=os.getenv("GEMINI_API_KEY", ""),
                models=["gemini-3.1-pro", "gemini-3.1-flash"]
            ),
            "deepseek": ProviderConfig(
                name="DeepSeek",
                base_url="https://api.deepseek.com",
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                models=["deepseek-chat", "deepseek-reasoner"]
            ),
            "moonshot": ProviderConfig(
                name="Kimi (月之暗面)",
                base_url="https://api.moonshot.cn/v1",
                api_key=os.getenv("MOONSHOT_API_KEY", ""),
                models=["kimi-k2.5", "kimi-k2"]
            ),
            "qwen": ProviderConfig(
                name="Qwen (通义千问)",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key=os.getenv("DASHSCOPE_API_KEY", ""),
                models=["qwen3.6-plus", "qwen3.5-plus", "qwen3-max"]
            ),
            "glm": ProviderConfig(
                name="GLM (智谱 AI)",
                base_url="https://open.bigmodel.cn/api/paas/v4",
                api_key=os.getenv("GLM_API_KEY", ""),
                models=["glm-5.1", "glm-4.7", "glm-4-flash"]
            ),
            "minimax": ProviderConfig(
                name="MiniMax",
                base_url="https://api.minimax.chat/v1",
                api_key=os.getenv("MINIMAX_API_KEY", ""),
                models=["minimax-m2.7", "abab7-chat"]
            ),
        }
    )
    return default_config


def load_config() -> ConfigData:
    """Load configuration from file or create default."""
    global _config
    
    if _config is not None:
        return _config
    
    config_path = get_config_path()
    
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f) or {}
        _config = ConfigData(**yaml_data)
    else:
        # Create default config
        _config = create_default_config()
        save_config(_config)
    
    return _config


def save_config(config: ConfigData) -> None:
    """Save configuration to file."""
    ensure_config_dir()
    config_path = get_config_path()
    
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False, allow_unicode=True)


def get_settings() -> Settings:
    """Get FastAPI settings."""
    global _settings
    
    if _settings is None:
        _settings = Settings()
    
    return _settings


def get_data_dir() -> Path:
    """Get data directory path."""
    config = load_config()
    data_dir = Path(config.data_dir).expanduser()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_database_path() -> Path:
    """Get SQLite database file path."""
    return get_data_dir() / "quantclass.db"


def reload_config() -> ConfigData:
    """Reload configuration from file."""
    global _config
    _config = None
    return load_config()
