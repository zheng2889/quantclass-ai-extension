"""Summary router."""

from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from models import (
    success, not_found, llm_error, param_error,
    SummaryGenerateRequest, SummaryResponse, SummaryDetailResponse,
    PaginationParams
)
from services import SummaryService

router = APIRouter(tags=["Summary"])


@router.post("/generate")
async def generate_summary(request: SummaryGenerateRequest):
    """Generate summary. Supports SSE streaming when stream=true."""
    if request.stream:
        return StreamingResponse(
            SummaryService.generate_summary_stream(
                thread_id=request.thread_id,
                title=request.title,
                content=request.content,
                model=request.model,
                auto_tags=request.auto_tags,
                language=request.language,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )
    try:
        result = await SummaryService.generate_summary(
            thread_id=request.thread_id,
            title=request.title,
            content=request.content,
            model=request.model,
            auto_tags=request.auto_tags,
            language=request.language,
        )
        return success(result)
    except ValueError as e:
        return param_error(str(e))
    except Exception as e:
        return llm_error(str(e))


@router.get("/{thread_id}")
async def get_summary(thread_id: str):
    """Get existing summary by thread_id."""
    result = await SummaryService.get_summary(thread_id)
    if result:
        return success(result)
    return not_found(f"Summary not found for thread: {thread_id}")


@router.get("/")
async def list_summaries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100)
):
    """List all summaries with pagination."""
    result = await SummaryService.list_summaries(page=page, page_size=page_size)
    return success(result)


@router.delete("/{thread_id}")
async def delete_summary(thread_id: str):
    """Delete summary by thread_id."""
    success_flag = await SummaryService.delete_summary(thread_id)
    if success_flag:
        return success({"deleted": True})
    return not_found(f"Summary not found for thread: {thread_id}")
