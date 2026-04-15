"""Chat router — persistent conversational AI with memory."""

import asyncio
import json
from typing import List, Optional
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from models import success, error, llm_error
from models.schemas import (
    ChatSessionCreate, ChatMessageInSession,
    PaginationParams,
)
from llm.adapter import llm_adapter
from llm.base import LLMMessage
from services.chat_service import chat_service
from services.memory_service import memory_service

router = APIRouter(tags=["Chat"])


# ── Legacy schema (kept for backward compat) ──

class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class ImageRef(BaseModel):
    base64: str = Field(..., description="data:image/png;base64,... URI")
    page: Optional[int] = None

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    context: Optional[str] = Field(default=None, description="Current page content for grounding")
    images: Optional[List[ImageRef]] = Field(default=None, description="PDF images for multimodal analysis")
    history: List[ChatMessage] = Field(default_factory=list)
    language: str = Field(default="中文")


# ── Legacy endpoint (deprecated, kept for old clients) ──

@router.post("")
async def chat_legacy(request: ChatRequest):
    """Legacy stateless chat. New clients should use /sessions/{id}/messages."""
    try:
        llm = llm_adapter.get_llm()
        messages = []

        if request.context:
            ctx = request.context[:60000]

            context_text = (
                f"我正在阅读一篇文档，以下是完整文本内容：\n\n"
                f"---\n{ctx}\n---\n\n"
                f"请基于这篇文档回答我之后的问题。用{request.language}回复，输出使用 Markdown 格式。"
            )

            if request.images and len(request.images) > 0:
                content_parts = [{"type": "text", "text": context_text}]
                for img in request.images[:10]:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": img.base64},
                    })
                content_parts.append({
                    "type": "text",
                    "text": f"以上是文档中提取的 {len(request.images)} 张图表/图片，请在分析时也参考这些图片内容。"
                })
                messages.append(LLMMessage(role="user", content=content_parts))
            else:
                messages.append(LLMMessage(role="user", content=context_text))

            messages.append(LLMMessage(
                role="assistant",
                content=f"好的，我已仔细阅读了这篇文档的文本内容" +
                        (f"和 {len(request.images)} 张图表" if request.images else "") +
                        "。请问有什么想了解的？",
            ))

        for msg in request.history[-10:]:
            messages.append(LLMMessage(role=msg.role, content=msg.content))
        messages.append(LLMMessage(role="user", content=request.message))

        response = await llm.chat(messages, temperature=0.5)
        return success({
            "reply": response.content,
            "model_used": response.model,
            "tokens_used": response.usage.total_tokens,
        })
    except Exception as e:
        return llm_error(str(e))


# ── Session-based endpoints (with memory injection) ──

@router.post("/sessions")
async def create_session(request: ChatSessionCreate):
    """Create a new chat session."""
    try:
        session_id = await chat_service.create_session(
            thread_id=request.thread_id,
            page_url=request.page_url,
            page_title=request.page_title,
        )
        session = await chat_service.get_session(session_id)
        return success(session)
    except Exception as e:
        return error(500, str(e))


@router.get("/sessions")
async def list_sessions(page: int = 1, page_size: int = 20):
    """List chat sessions."""
    try:
        result = await chat_service.list_sessions(page, page_size)
        return success(result)
    except Exception as e:
        return error(500, str(e))


@router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a chat session with all messages."""
    session = await chat_service.get_session(session_id)
    if not session:
        return error(404, "Session not found")
    return success(session)


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    await chat_service.generate_session_summary(session_id)
    deleted = await chat_service.delete_session(session_id)
    if not deleted:
        return error(404, "Session not found")
    return success({"deleted": True})


async def _build_session_messages(session: dict, request: ChatMessageInSession):
    """Assemble the LLMMessage list for an in-session chat request.

    Returns ``(messages, memory_context_text)``. Separated from the HTTP
    handler so the streaming and non-streaming paths can share prep logic.
    """
    session_id = session["id"]
    messages: list[LLMMessage] = []

    # 1. Inject memory context
    memory_context = await memory_service.build_memory_context(
        thread_id=session.get("thread_id"), max_tokens=1500
    )
    if memory_context:
        messages.append(LLMMessage(
            role="user",
            content=f"以下是你对我的了解，请在回答时参考：\n\n{memory_context}\n\n请确认你已了解。",
        ))
        messages.append(LLMMessage(
            role="assistant",
            content="好的，我已了解你的背景和偏好，会据此给出更有针对性的回答。",
        ))

    # 2. Inject page context
    if request.context:
        ctx = request.context[:6000]
        messages.append(LLMMessage(
            role="user",
            content=(
                f"我正在阅读一篇量化论坛帖子，以下是帖子内容：\n\n"
                f"---\n{ctx}\n---\n\n"
                f"请基于这篇帖子内容回答我之后的问题。用{request.language}回复，输出使用 Markdown 格式。"
            ),
        ))
        messages.append(LLMMessage(
            role="assistant",
            content="好的，我已仔细阅读了这篇帖子。请问有什么想了解的？",
        ))

    # 3. Inject recent history
    recent = await chat_service.get_recent_messages(session_id, limit=10)
    for msg in recent:
        messages.append(LLMMessage(role=msg["role"], content=msg["content"]))

    # 4. Current message
    messages.append(LLMMessage(role="user", content=request.message))
    return messages, memory_context


def _sse(event: dict) -> str:
    """Serialize one SSE event. Always newline-terminated per spec."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/sessions/{session_id}/messages")
async def chat_in_session(session_id: str, request: ChatMessageInSession):
    """Send a message in a session with memory-augmented context.

    When ``stream=true`` returns a Server-Sent Events stream:
        data: {"type":"chunk","content":"..."}\\n\\n
        data: {"type":"chunk","content":"..."}\\n\\n
        ...
        data: {"type":"done","message_id":"...","tokens_used":123,"memory_active":true}\\n\\n

    Otherwise returns the legacy single-shot JSON envelope.
    """
    session = await chat_service.get_session(session_id)
    if not session:
        return error(404, "Session not found")

    # ── Streaming path ───────────────────────────────────────────────
    if request.stream:
        async def event_generator():
            try:
                messages, memory_context = await _build_session_messages(session, request)
                llm = llm_adapter.get_llm()

                # Persist the user message first so it shows up in history
                # even if the stream dies mid-way.
                await chat_service.add_message(session_id, "user", request.message)

                buffer: list[str] = []
                async for chunk in llm.chat_stream(messages, temperature=0.5):
                    if chunk:
                        buffer.append(chunk)
                        yield _sse({"type": "chunk", "content": chunk})

                full_content = "".join(buffer)
                # Persist assistant reply. We don't have an exact token count
                # from the streaming path (provider-dependent), so pass 0 and
                # let callers treat it as "unknown".
                msg_id = await chat_service.add_message(
                    session_id, "assistant", full_content, 0
                )

                # Async memory extraction every 10 messages
                msg_count = session.get("message_count", 0) + 2
                if msg_count % 10 == 0:
                    asyncio.create_task(
                        memory_service.extract_memories_from_conversation(session_id)
                    )

                yield _sse({
                    "type": "done",
                    "message_id": msg_id,
                    "memory_active": bool(memory_context),
                })
            except Exception as e:
                yield _sse({"type": "error", "message": str(e)})

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering if fronted
                "Connection": "keep-alive",
            },
        )

    # ── Legacy non-streaming path ────────────────────────────────────
    try:
        messages, memory_context = await _build_session_messages(session, request)
        llm = llm_adapter.get_llm()
        response = await llm.chat(messages, temperature=0.5)

        await chat_service.add_message(session_id, "user", request.message)
        msg_id = await chat_service.add_message(
            session_id, "assistant", response.content, response.usage.total_tokens
        )

        msg_count = session.get("message_count", 0) + 2
        if msg_count % 10 == 0:
            asyncio.create_task(
                memory_service.extract_memories_from_conversation(session_id)
            )

        return success({
            "reply": response.content,
            "message_id": msg_id,
            "model_used": response.model,
            "tokens_used": response.usage.total_tokens,
            "memory_active": bool(memory_context),
        })
    except Exception as e:
        return llm_error(str(e))


@router.get("/search")
async def search_conversations(q: str = "", limit: int = 20):
    """Search across all conversation history."""
    if not q.strip():
        return success({"results": []})
    try:
        results = await chat_service.search_conversations(q, limit)
        return success({"results": results})
    except Exception as e:
        return error(500, str(e))
