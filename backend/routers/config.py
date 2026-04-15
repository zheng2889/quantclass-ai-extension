"""Config router - read/update backend configuration.

GET  /api/config     → sanitized config (no raw api_keys, only a `has_api_key` flag).
PUT  /api/config     → partial update of default_model / default_provider / providers.
                       API keys in the request body are applied verbatim.
"""

from fastapi import APIRouter
from models import (
    success,
    param_error,
    internal_error,
    ConfigResponse,
    ConfigUpdateRequest,
    ProviderInfo,
)
from typing import Optional as Opt
from pydantic import BaseModel as BM2, Field as F2
from config import load_config, save_config, reload_config, ProviderConfig
from llm.adapter import llm_adapter
from llm.base import LLMMessage

router = APIRouter(tags=["Config"])


def _sanitize(config) -> dict:
    """Convert ConfigData to a client-safe dict (no raw API keys)."""
    providers = {}
    for pid, p in config.providers.items():
        providers[pid] = ProviderInfo(
            name=p.name,
            base_url=p.base_url,
            models=list(p.models),
            builtin=False,
            has_api_key=bool(p.api_key and p.api_key.strip()),
            protocol=getattr(p, 'protocol', 'openai') or 'openai',
        ).model_dump()

    return {
        "host": config.host,
        "port": config.port,
        "data_dir": config.data_dir,
        "default_model": config.default_model,
        "default_provider": config.default_provider,
        "providers": providers,
    }


@router.get("")
async def get_config():
    """Return the current backend config, with api_keys redacted."""
    try:
        config = load_config()
        return success(_sanitize(config))
    except Exception as e:
        return internal_error(str(e))


@router.put("")
async def update_config(request: ConfigUpdateRequest):
    """Apply a partial config update and persist to ~/.quantclass/config.yaml.

    Clears the LLM adapter cache so the next request picks up the new settings.
    """
    try:
        config = load_config()

        if request.default_provider is not None:
            if request.default_provider not in config.providers:
                return param_error(
                    f"Unknown provider: {request.default_provider}"
                )
            config.default_provider = request.default_provider

        if request.default_model is not None:
            config.default_model = request.default_model

        if request.data_dir is not None:
            config.data_dir = request.data_dir
            # Ensure the new directory exists
            from services.md_storage import ensure_knowledge_dirs
            ensure_knowledge_dirs()

        if request.providers:
            for pid, update in request.providers.items():
                if pid in config.providers:
                    # Update existing provider
                    existing = config.providers[pid]
                    config.providers[pid] = ProviderConfig(
                        name=update.name if update.name is not None else existing.name,
                        base_url=update.base_url if update.base_url is not None else existing.base_url,
                        api_key=update.api_key if update.api_key is not None else existing.api_key,
                        models=update.models if update.models is not None else existing.models,
                        protocol=update.protocol if update.protocol is not None else getattr(existing, 'protocol', 'openai'),
                    )
                else:
                    # Create new custom provider (requires at least base_url)
                    if update.base_url:
                        config.providers[pid] = ProviderConfig(
                            name=update.name or pid,
                            base_url=update.base_url,
                            api_key=update.api_key or "",
                            models=update.models or [],
                            protocol=update.protocol or "openai",
                        )

        # Handle provider deletion
        if request.delete_providers:
            for pid in request.delete_providers:
                if pid in config.providers:
                    del config.providers[pid]

        save_config(config)

        # Reload singleton and invalidate LLM adapter cache so next call uses new config
        reload_config()
        try:
            llm_adapter._llm_cache.clear()
        except Exception:
            pass

        return success(_sanitize(load_config()))
    except Exception as e:
        return internal_error(str(e))


class TestProviderRequest(BM2):
    provider: str = F2(..., min_length=1)
    model: Opt[str] = None


@router.post("/test-provider")
async def test_provider(request: TestProviderRequest):
    """Test a specific provider by sending a minimal chat request."""
    try:
        config = load_config()
        if request.provider not in config.providers:
            return param_error(f"Unknown provider: {request.provider}")

        pc = config.providers[request.provider]
        model = request.model or (pc.models[0] if pc.models else None)
        if not model:
            return param_error("No model specified and provider has no default models")

        if not pc.api_key:
            return param_error(f"No API key configured for {request.provider}")

        # Get or create LLM instance for this specific provider + model
        llm = llm_adapter.get_llm(provider=request.provider, model=model)
        messages = [LLMMessage(role="user", content="Say 'ok' in one word.")]
        # Some models (Kimi k2.5) only allow temperature=1
        resp = await llm.chat(messages, temperature=1, max_tokens=5)

        return success({
            "provider": request.provider,
            "model": model,
            "response": resp.content[:50],
            "tokens": resp.usage.total_tokens if resp.usage else 0,
        })
    except Exception as e:
        return internal_error(f"{request.provider}: {str(e)}")
