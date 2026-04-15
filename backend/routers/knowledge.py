"""Knowledge (bookmarks) router."""

from typing import Optional, Literal
from fastapi import APIRouter, Query, Response
from models import (
    success, not_found, param_error, already_exists,
    BookmarkCreateRequest, BookmarkUpdateRequest, BookmarkResponse,
    BookmarkDetailResponse, BookmarkListRequest, BookmarkListResponse,
    NoteCreateRequest, NoteUpdateRequest, NoteResponse,
    ExportFormat, PaginationParams
)
from services import KnowledgeService

router = APIRouter(tags=["Knowledge"])


@router.post("/bookmarks")
async def create_bookmark(request: BookmarkCreateRequest):
    """Create a new bookmark."""
    try:
        result = await KnowledgeService.create_bookmark(
            thread_id=request.thread_id,
            title=request.title,
            url=request.url,
            summary=request.summary,
            tags=request.tags
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.get("/bookmarks")
async def list_bookmarks(
    tag: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: Literal["created", "updated", "title"] = "created",
    sort_order: Literal["asc", "desc"] = "desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """List bookmarks with filtering."""
    result = await KnowledgeService.list_bookmarks(
        tag=tag,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size
    )
    return success(result)


@router.get("/bookmarks/{bookmark_id}")
async def get_bookmark(bookmark_id: str):
    """Get bookmark by ID."""
    result = await KnowledgeService.get_bookmark(bookmark_id)
    if result:
        return success(result)
    return not_found(f"Bookmark not found: {bookmark_id}")


@router.put("/bookmarks/{bookmark_id}")
async def update_bookmark(bookmark_id: str, request: BookmarkUpdateRequest):
    """Update bookmark."""
    result = await KnowledgeService.update_bookmark(
        bookmark_id=bookmark_id,
        title=request.title,
        url=request.url,
        summary=request.summary,
        tags=request.tags
    )
    if result:
        return success(result)
    return not_found(f"Bookmark not found: {bookmark_id}")


@router.delete("/bookmarks/{bookmark_id}")
async def delete_bookmark(bookmark_id: str):
    """Delete bookmark."""
    success_flag = await KnowledgeService.delete_bookmark(bookmark_id)
    if success_flag:
        return success({"deleted": True})
    return not_found(f"Bookmark not found: {bookmark_id}")


# ============== Notes ==============

@router.post("/bookmarks/{bookmark_id}/notes")
async def add_note(bookmark_id: str, request: NoteCreateRequest):
    """Add note to bookmark."""
    result = await KnowledgeService.add_note(bookmark_id, request.content)
    if result:
        return success(result)
    return not_found(f"Bookmark not found: {bookmark_id}")


@router.get("/bookmarks/{bookmark_id}/notes")
async def get_note(bookmark_id: str):
    """Get note for bookmark."""
    result = await KnowledgeService.get_note(bookmark_id)
    if result:
        return success(result)
    return not_found(f"Note not found for bookmark: {bookmark_id}")


# ============== Export ==============

@router.get("/export")
async def export_bookmarks(
    format: Literal["json", "markdown", "csv"] = "json",
    include_notes: bool = True,
    include_tags: bool = True
):
    """Export bookmarks to various formats."""
    try:
        content = await KnowledgeService.export_bookmarks(format=format)
        
        # Set appropriate content type and headers
        if format == "json":
            media_type = "application/json"
            filename = "bookmarks.json"
        elif format == "csv":
            media_type = "text/csv"
            filename = "bookmarks.csv"
        else:  # markdown
            media_type = "text/markdown"
            filename = "bookmarks.md"
        
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return param_error(str(e))
