"""Summary generation service."""

import hashlib
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta, timezone

_CST = timezone(timedelta(hours=8))

from database.connection import db
from llm.adapter import llm_adapter
from llm.prompts import get_prompt, SUMMARY_PROMPT, TAG_SUGGESTION_PROMPT
from services.md_storage import save_md, delete_md, resolve_content
from llm.base import LLMMessage


class SummaryService:
    """Service for summary generation and management."""
    
    @staticmethod
    def _compute_hash(content: str) -> str:
        """Compute content hash."""
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    @staticmethod
    def _truncate_content(content: str) -> str:
        """超过 8000 字时，保留首尾各 3000 字，中间用省略提示替代（规范：首尾各 3000 字）。"""
        if len(content) <= 8000:
            return content
        head = content[:3000]
        tail = content[-3000:]
        omitted = len(content) - 6000
        return f"{head}\n\n...[中间省略 {omitted} 字]...\n\n{tail}"
    
    @staticmethod
    def _now_iso() -> str:
        """Current time as an ISO-8601 string in the +08:00 zone used by the DB."""
        return datetime.now(_CST).strftime("%Y-%m-%dT%H:%M:%S+08:00")

    @staticmethod
    async def get_summary(
        thread_id: str,
        include_expired: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Get existing summary by thread_id.

        By default expired rows (``expires_at`` in the past) are treated as a
        cache miss, matching the 30-day TTL promised in the PRD. Pass
        ``include_expired=True`` from admin / cleanup paths that need to see
        the raw row regardless of its freshness.
        """
        row = await db.fetchone(
            "SELECT * FROM summaries WHERE thread_id = ?",
            (thread_id,)
        )
        if not row:
            return None

        data = dict(row)
        # Resolve DB path → file content (backward compat: inline text passes through)
        data["summary"] = resolve_content(data.get("summary"))

        if include_expired:
            return data

        expires_at = data.get("expires_at")
        if expires_at and expires_at <= SummaryService._now_iso():
            return None
        return data

    @staticmethod
    async def cleanup_expired_summaries() -> int:
        """Delete all summaries whose ``expires_at`` is in the past.

        Returns the number of rows removed. Safe to call repeatedly; meant to
        run at startup to keep the DB bounded without pulling in a scheduler.
        """
        cursor = await db.execute(
            "DELETE FROM summaries WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (SummaryService._now_iso(),),
        )
        return cursor.rowcount or 0
    
    @staticmethod
    async def generate_summary(
        thread_id: str,
        title: str,
        content: str,
        model: Optional[str] = None,
        auto_tags: bool = True,
        language: str = "中文",
    ) -> Dict[str, Any]:
        """Generate or retrieve summary for content."""
        content_hash = SummaryService._compute_hash(content)

        # Include expired rows here so we can distinguish "row exists but
        # stale" (→ UPDATE path) from "row never existed" (→ INSERT path).
        # Callers that want cache-hit semantics should use get_summary() with
        # the default include_expired=False.
        existing = await SummaryService.get_summary(thread_id, include_expired=True)
        if existing and existing["content_hash"] == content_hash:
            expires_at = existing.get("expires_at")
            if not expires_at or expires_at > SummaryService._now_iso():
                return existing
            # Same content but TTL elapsed: refresh expiry in place without
            # calling the LLM again.
            new_expires = (datetime.now() + timedelta(days=30)).isoformat()
            await db.execute(
                "UPDATE summaries SET expires_at = ? WHERE thread_id = ?",
                (new_expires, thread_id),
            )
            existing["expires_at"] = new_expires
            return existing
        
        # Generate summary using LLM
        llm = llm_adapter.get_llm(model=model)
        
        truncated = SummaryService._truncate_content(content)
        prompt = get_prompt(SUMMARY_PROMPT, title=title, content=truncated, language=language)
        messages = [LLMMessage(role="user", content=prompt)]
        
        response = await llm.chat(messages, temperature=0.3)
        
        # Generate tags if requested
        tags = []
        if auto_tags:
            tags = await SummaryService._generate_tags(content, response.content)
        
        # Write summary to MD file; DB stores the relative path.
        summary_path = save_md("summaries", thread_id, response.content)

        summary_data = {
            "thread_id": thread_id,
            "title": title,
            "content_hash": content_hash,
            "summary": response.content,  # return actual text to caller
            "auto_tags": json.dumps(tags),
            "model_used": response.model,
            "tokens_used": response.usage.total_tokens,
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat()
        }

        # UPSERT: DB summary column stores the *file path*, not the text.
        await db.execute(
            """INSERT INTO summaries
               (thread_id, title, content_hash, summary, auto_tags,
                model_used, tokens_used, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(thread_id) DO UPDATE SET
                 title = excluded.title,
                 content_hash = excluded.content_hash,
                 summary = excluded.summary,
                 auto_tags = excluded.auto_tags,
                 model_used = excluded.model_used,
                 tokens_used = excluded.tokens_used,
                 expires_at = excluded.expires_at,
                 updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')""",
            (thread_id, title, content_hash, summary_path, json.dumps(tags),
             response.model, response.usage.total_tokens, summary_data["expires_at"])
        )

        return summary_data
    
    @staticmethod
    async def generate_summary_stream(
        thread_id: str,
        title: str,
        content: str,
        model: Optional[str] = None,
        auto_tags: bool = True,
        language: str = "中文",
    ):
        """Generate summary with SSE streaming. Yields SSE-formatted strings."""
        content_hash = SummaryService._compute_hash(content)
        truncated = SummaryService._truncate_content(content)

        # Check cache first (fresh cache only; expired rows fall through and
        # regenerate below).
        existing = await SummaryService.get_summary(thread_id)
        if existing and existing.get("content_hash") == content_hash:
            # Stream cached content
            summary_text = existing.get("summary", "")
            # Send cached content as single chunk
            payload = json.dumps({"type": "chunk", "text": summary_text}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            # Send cached tags
            cached_tags = json.loads(existing.get("auto_tags", "[]"))
            payload = json.dumps({"type": "tags", "tags": cached_tags}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            # Send done
            payload = json.dumps({"type": "done", "tokens_used": existing.get("tokens_used", 0), "cached": True}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
            return

        llm = llm_adapter.get_llm(model=model)
        prompt = get_prompt(SUMMARY_PROMPT, title=title, content=truncated, language=language)
        messages = [LLMMessage(role="user", content=prompt)]

        full_text = ""
        tokens_used = 0

        try:
            # Stream summary chunks
            async for chunk in llm.chat_stream(messages, temperature=0.3):
                full_text += chunk
                tokens_used += 1  # approximation
                payload = json.dumps({"type": "chunk", "text": chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"

            # Generate tags
            tags = []
            if auto_tags:
                tags = await SummaryService._generate_tags(content, full_text)
                payload = json.dumps({"type": "tags", "tags": tags}, ensure_ascii=False)
                yield f"data: {payload}\n\n"

            # Save to database. Use include_expired=True so an expired row
            # with the same thread_id takes the UPDATE path instead of
            # tripping the UNIQUE constraint on INSERT. Always refresh
            # expires_at — a regenerated row starts a new 30-day window.
            # Write to MD file; DB stores path
            summary_path = save_md("summaries", thread_id, full_text)
            expires_at = (datetime.now() + timedelta(days=30)).isoformat()
            await db.execute(
                """INSERT INTO summaries
                   (thread_id, title, content_hash, summary, auto_tags,
                    model_used, tokens_used, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(thread_id) DO UPDATE SET
                     title = excluded.title,
                     content_hash = excluded.content_hash,
                     summary = excluded.summary,
                     auto_tags = excluded.auto_tags,
                     model_used = excluded.model_used,
                     tokens_used = excluded.tokens_used,
                     expires_at = excluded.expires_at,
                     updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')""",
                (thread_id, title, content_hash, summary_path, json.dumps(tags),
                 llm.model, tokens_used, expires_at)
            )

            # Done event
            payload = json.dumps({"type": "done", "tokens_used": tokens_used}, ensure_ascii=False)
            yield f"data: {payload}\n\n"
        except Exception as e:
            payload = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {payload}\n\n"

    @staticmethod
    async def _generate_tags(content: str, summary: str) -> List[str]:
        """Generate tags for content."""
        try:
            llm = llm_adapter.get_llm()
            
            combined_content = f"Summary: {summary}\n\nOriginal Content:\n{content[:4000]}"
            
            prompt = get_prompt(
                TAG_SUGGESTION_PROMPT,
                content=combined_content,
                existing_tags="",
                max_suggestions=5
            )
            messages = [LLMMessage(role="user", content=prompt)]
            
            response = await llm.chat(messages, temperature=0.3)
            
            # Parse tags from response
            tags = [t.strip() for t in response.content.split(",") if t.strip()]
            return tags[:5]
        except Exception:
            return []
    
    @staticmethod
    async def delete_summary(thread_id: str) -> bool:
        """Delete summary by thread_id + its MD file."""
        # Read the path before deleting the row
        row = await db.fetchone(
            "SELECT summary FROM summaries WHERE thread_id = ?",
            (thread_id,),
        )
        result = await db.execute(
            "DELETE FROM summaries WHERE thread_id = ?",
            (thread_id,)
        )
        if result.rowcount > 0 and row:
            delete_md(row["summary"])  # safe if it's inline text (no-op)
            return True
        return False
    
    @staticmethod
    async def list_summaries(
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """List all summaries with pagination."""
        offset = (page - 1) * page_size
        
        total = await db.fetchval("SELECT COUNT(*) FROM summaries")
        
        rows = await db.fetchall(
            """SELECT thread_id, title, summary, auto_tags, model_used, 
                      tokens_used, created_at, updated_at
               FROM summaries
               ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, offset)
        )
        
        items = []
        for row in rows:
            item = dict(row)
            item["summary"] = resolve_content(item.get("summary"))
            item["auto_tags"] = json.loads(item.get("auto_tags", "[]"))
            items.append(item)
        
        total_pages = (total + page_size - 1) // page_size
        
        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }
