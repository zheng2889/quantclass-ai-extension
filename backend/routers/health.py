"""Health check router."""

from fastapi import APIRouter
from models import success
from config import load_config
from database.connection import db

router = APIRouter(tags=["Health"])


@router.get("")
async def health_check():
    """Health check endpoint - matches API spec."""
    config = load_config()

    # Check SQLite connectivity
    sqlite_status = "disconnected"
    try:
        await db.fetchval("SELECT 1")
        sqlite_status = "connected"
    except Exception:
        pass

    # Check LLM configuration
    llm_configured = False
    try:
        default_provider = config.default_provider
        provider_cfg = config.providers.get(default_provider)
        if provider_cfg and provider_cfg.api_key:
            llm_configured = True
    except Exception:
        pass

    return success({
        "status": "healthy",
        "version": "0.1.0",
        "sqlite": sqlite_status,
        "chromadb": "not_configured",   # ChromaDB 为可选组件，当前未启用
        "llm_configured": llm_configured,
        "default_model": config.default_model,
    })


@router.get("/ready")
async def readiness_check():
    """Readiness check."""
    return success({"ready": True})
