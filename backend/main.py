"""QuantClass Backend - FastAPI Application Entry Point"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


from config import get_settings, load_config, ensure_config_dir
from database import init_database, close_database
from routers import api_router
from models import BaseResponse, success, error, ResponseCode
from services.summary_service import SummaryService
from services.md_storage import ensure_knowledge_dirs
from services.agent_service import ensure_default_agents


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    ensure_config_dir()
    await init_database()
    config = load_config()
    ensure_knowledge_dirs()
    ensure_default_agents()
    print(f"🚀 QuantClass Backend starting on {config.host}:{config.port}")
    print(f"📁 Data directory: {config.data_dir}")
    print(f"🤖 Default model: {config.default_model}")
    # One-shot cleanup of summaries past their 30-day TTL. We don't run a
    # scheduler — a single sweep at startup is enough for a local tool that
    # gets restarted regularly, and it keeps the DB bounded without extra
    # dependencies.
    try:
        removed = await SummaryService.cleanup_expired_summaries()
        if removed:
            print(f"🧹 Pruned {removed} expired summary row(s)")
    except Exception as e:
        print(f"⚠️  Summary cleanup skipped: {e}")
    yield
    # Shutdown
    await close_database()
    print("👋 QuantClass Backend shutting down")


# Create FastAPI app
settings = get_settings()

app = FastAPI(
    title="QuantClass Backend",
    description="Smart Browser Extension Backend API for Quantitative Finance",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Add CORS middleware
_ALLOWED_ORIGINS = [
    "http://127.0.0.1:8700",
    "http://localhost:8700",
    "null",  # Chrome extension pages send null origin
]

_extra = os.getenv("QUANTCLASS_CORS_ORIGINS", "")
if _extra:
    _ALLOWED_ORIGINS.extend(o.strip() for o in _extra.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Handle all unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content=error(
            code=ResponseCode.INTERNAL_ERROR,
            message="Internal server error",
            data={"detail": str(exc)}
        ).model_dump()
    )


# Include all routers
app.include_router(api_router)


@app.get("/")
async def root():
    """Root endpoint."""
    return success({
        "service": "QuantClass Backend",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/health"
    })


@app.get("/health")
async def simple_health():
    """Simple health check at root."""
    return success({"status": "healthy"})


if __name__ == "__main__":
    import uvicorn
    config = load_config()
    uvicorn.run(
        "main:app",
        host=config.host,
        port=config.port,
        reload=settings.debug,
        log_level="info"
    )
