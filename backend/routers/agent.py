"""Agent router — CRUD for agent personas + multi-agent discussion."""

import json
from typing import List, Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from models import success, param_error, not_found, internal_error
from services.agent_service import (
    list_agents, get_agent, create_agent, update_agent,
    delete_agent, discuss, discuss_stream,
)

router = APIRouter(tags=["Agent"])


class AgentCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-z0-9_]+$')
    name: str = Field(..., min_length=1)
    icon: str = Field(default="🤖")
    description: str = Field(default="")
    prompt: str = Field(..., min_length=1)
    enabled: bool = Field(default=True)
    order: int = Field(default=99)


class AgentUpdateRequest(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    enabled: Optional[bool] = None
    order: Optional[int] = None


class DiscussRequest(BaseModel):
    question: str = Field(..., min_length=1)
    context: Optional[str] = Field(default=None)
    agents: List[str] = Field(..., min_length=1)
    language: str = Field(default="中文")
    stream: bool = Field(default=False, description="Return text/event-stream instead of JSON")


@router.get("")
async def get_agents():
    """List all available agents."""
    try:
        return success(list_agents())
    except Exception as e:
        return internal_error(str(e))


@router.get("/{agent_id}")
async def get_agent_detail(agent_id: str):
    agent = get_agent(agent_id)
    if not agent:
        return not_found(f"Agent not found: {agent_id}")
    return success(agent)


@router.post("")
async def create_new_agent(request: AgentCreateRequest):
    try:
        result = create_agent(request.id, request.model_dump())
        return success(result)
    except Exception as e:
        return internal_error(str(e))


@router.put("/{agent_id}")
async def update_existing_agent(agent_id: str, request: AgentUpdateRequest):
    result = update_agent(agent_id, request.model_dump(exclude_none=True))
    if not result:
        return not_found(f"Agent not found: {agent_id}")
    return success(result)


@router.delete("/{agent_id}")
async def delete_existing_agent(agent_id: str):
    if delete_agent(agent_id):
        return success({"deleted": True})
    return not_found(f"Agent not found: {agent_id}")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/discuss")
async def discuss_with_agents(request: DiscussRequest):
    """Run a multi-agent round-table discussion.

    When ``stream=true`` returns a text/event-stream where events from N
    parallel agents are interleaved as they arrive — clients can render
    chunks into the right agent bubble by matching ``agent_id``.
    """
    if request.stream:
        async def event_generator():
            try:
                async for event in discuss_stream(
                    question=request.question,
                    context=request.context or "",
                    agent_ids=request.agents,
                    language=request.language,
                ):
                    yield _sse(event)
            except Exception as e:
                yield _sse({"type": "error", "message": str(e)})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    try:
        responses = await discuss(
            question=request.question,
            context=request.context or "",
            agent_ids=request.agents,
            language=request.language,
        )
        return success({"responses": responses})
    except Exception as e:
        return internal_error(str(e))
