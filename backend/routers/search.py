"""Search router."""

from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Query
from models import (
    success, param_error,
    SearchRequest, SearchResponse, PaginationParams
)
from services import SearchService

router = APIRouter(tags=["Search"])


@router.post("")
async def search(request: SearchRequest):
    """Search bookmarks using FTS5."""
    try:
        result = await SearchService.search(
            query=request.query,
            filters=request.filters,
            page=request.pagination.page,
            page_size=request.pagination.page_size
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.get("")
async def search_get(
    q: str = Query(..., description="Search query"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """Search bookmarks (GET method for convenience)."""
    try:
        result = await SearchService.search(
            query=q,
            page=page,
            page_size=page_size
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.post("/advanced")
async def advanced_search(
    title: Optional[str] = Query(default=None),
    content: Optional[str] = Query(default=None),
    # List[str] query params MUST be wrapped in Query(), otherwise FastAPI
    # tries to bind them from the request body on a POST and silently
    # ignores repeated ?tags=a&tags=b query strings. The filter then
    # no-ops in production — a real bug found via integration tests.
    tags: Optional[List[str]] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """Advanced search with multiple filters."""
    try:
        result = await SearchService.advanced_search(
            title=title,
            content=content,
            tags=tags,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))
