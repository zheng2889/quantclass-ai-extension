"""Tags router."""

from typing import Optional
from fastapi import APIRouter, Query
from models import (
    success, not_found, param_error,
    TagSuggestRequest, TagSuggestResponse,
    TagCreateRequest, TagResponse, TagListResponse,
    PaginationParams
)
from services import TagService

router = APIRouter(tags=["Tags"])


@router.post("/suggest")
async def suggest_tags(request: TagSuggestRequest):
    """Suggest tags based on content."""
    try:
        suggestions = await TagService.suggest_tags(
            content=request.content,
            existing_tags=request.existing_tags,
            max_suggestions=request.max_suggestions
        )
        return success({"suggested_tags": suggestions})
    except Exception as e:
        return param_error(str(e))


@router.get("/")
async def list_tags(category: Optional[str] = None):
    """List all tags, optionally filtered by category."""
    result = await TagService.list_tags(category=category)
    return success(result)


@router.post("/")
async def create_tag(request: TagCreateRequest):
    """Create a new tag."""
    try:
        result = await TagService.create_tag(
            name=request.name,
            category=request.category
        )
        return success(result)
    except Exception as e:
        return param_error(str(e))


@router.get("/{tag_id}")
async def get_tag(tag_id: int):
    """Get tag by ID."""
    result = await TagService.get_tag(tag_id)
    if result:
        return success(result)
    return not_found(f"Tag not found: {tag_id}")


@router.delete("/{tag_id}")
async def delete_tag(tag_id: int):
    """Delete a tag."""
    success_flag = await TagService.delete_tag(tag_id)
    if success_flag:
        return success({"deleted": True})
    return not_found(f"Tag not found: {tag_id}")
