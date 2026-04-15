"""Memory management router — user profile, memory items, reading history, strategies."""

from fastapi import APIRouter
from models import success, error
from models.schemas import (
    UserProfileUpdateRequest, MemoryItemCreate,
    ReadingEventRequest, StrategyExtractRequest,
)
from services.memory_service import memory_service
from services.reading_service import reading_service
from services.strategy_service import strategy_service
from database.connection import db

router = APIRouter(tags=["Memory"])


# ── User Profile ──

@router.get("/profile")
async def get_profile():
    """Get user profile."""
    items = await memory_service.get_user_profile()
    return success({"items": items})


@router.post("/profile")
async def update_profile(request: UserProfileUpdateRequest):
    """Update user profile items."""
    for item in request.items:
        await memory_service.set_profile_item(
            profile_key=item.profile_key,
            profile_value=item.profile_value,
            source=item.source,
            confidence=item.confidence,
        )
    items = await memory_service.get_user_profile()
    return success({"items": items})


# ── Memory Items ──

@router.get("/items")
async def list_memories():
    """List all active memory items."""
    items = await memory_service.list_memories()
    return success({"items": items})


@router.post("/items")
async def add_memory(request: MemoryItemCreate):
    """Manually add a memory item."""
    mem_id = await memory_service.add_memory(
        memory_type=request.memory_type,
        content=request.content,
        importance=request.importance,
        source_thread_id=request.source_thread_id,
    )
    return success({"id": mem_id})


@router.delete("/items/{memory_id}")
async def delete_memory(memory_id: int):
    """Delete or deactivate a memory item."""
    deleted = await memory_service.delete_memory(memory_id)
    if not deleted:
        return error(404, "Memory item not found")
    return success({"deleted": True})


# ── Reading History ──

@router.post("/reading-history")
async def record_reading(request: ReadingEventRequest):
    """Record a reading event from the content script."""
    record_id = await reading_service.record_visit(
        thread_id=request.thread_id,
        title=request.title,
        url=request.url,
        duration_seconds=request.duration_seconds,
        scroll_depth=request.scroll_depth,
    )
    return success({"id": record_id})


@router.get("/reading-history")
async def get_reading_history(limit: int = 20):
    """Get recent reading history."""
    reads = await reading_service.get_recent_reads(limit)
    return success({"items": reads})


# ── Strategy Entities ──

@router.post("/extract-strategy")
async def extract_strategy(request: StrategyExtractRequest):
    """Extract strategy entity from post content."""
    result = await strategy_service.extract_from_content(
        thread_id=request.thread_id,
        title=request.title,
        content=request.content,
    )
    if result is None:
        return success({"extracted": False, "message": "No strategy found in content"})
    return success({"extracted": True, "strategy": result})


@router.get("/strategies")
async def list_strategies(strategy_type: str = None, asset_class: str = None,
                           page: int = 1, page_size: int = 20):
    """List extracted strategies."""
    result = await strategy_service.list_strategies(
        strategy_type=strategy_type,
        asset_class=asset_class,
        page=page,
        page_size=page_size,
    )
    return success(result)


@router.get("/strategies/{thread_id}")
async def get_strategies_for_thread(thread_id: str):
    """Get strategies extracted from a specific thread."""
    items = await strategy_service.get_strategies_for_thread(thread_id)
    return success({"items": items})


# ── Stats ──

@router.get("/stats")
async def get_memory_stats():
    """Get memory system statistics."""
    total_memories = await db.fetchval("SELECT COUNT(*) FROM memory_items")
    active_memories = await db.fetchval("SELECT COUNT(*) FROM memory_items WHERE is_active = 1")
    total_readings = await db.fetchval("SELECT COUNT(*) FROM reading_history")
    total_sessions = await db.fetchval("SELECT COUNT(*) FROM chat_sessions")
    total_strategies = await db.fetchval("SELECT COUNT(*) FROM strategy_entities")
    profile_keys = await db.fetchval("SELECT COUNT(*) FROM user_profile")

    reading_stats = await reading_service.get_reading_stats()

    return success({
        "total_memories": total_memories,
        "active_memories": active_memories,
        "total_readings": total_readings,
        "total_sessions": total_sessions,
        "total_strategies": total_strategies,
        "profile_keys": profile_keys,
        "reading_stats": reading_stats,
    })
