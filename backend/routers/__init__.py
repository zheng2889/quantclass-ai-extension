"""Routers module."""

from fastapi import APIRouter

from routers.health import router as health_router
from routers.summary import router as summary_router
from routers.tags import router as tags_router
from routers.knowledge import router as knowledge_router
from routers.search import router as search_router
from routers.assist import router as assist_router
from routers.admin import router as admin_router
from routers.auth import router as auth_router
from routers.config import router as config_router
from routers.chat import router as chat_router
from routers.pdf import router as pdf_router
from routers.agent import router as agent_router
from routers.memory import router as memory_router

# Create main API router
api_router = APIRouter(prefix="/api")

# Include all routers
api_router.include_router(health_router, prefix="/health")
api_router.include_router(summary_router, prefix="/summary")
api_router.include_router(tags_router, prefix="/tags")
api_router.include_router(knowledge_router, prefix="/knowledge")
api_router.include_router(search_router, prefix="/search")
api_router.include_router(assist_router, prefix="/assist")
api_router.include_router(admin_router, prefix="/admin")
api_router.include_router(auth_router, prefix="/auth")
api_router.include_router(config_router, prefix="/config")
api_router.include_router(chat_router, prefix="/chat")
api_router.include_router(pdf_router, prefix="/pdf")
api_router.include_router(agent_router, prefix="/agents")
api_router.include_router(memory_router, prefix="/memory")

__all__ = ["api_router"]
