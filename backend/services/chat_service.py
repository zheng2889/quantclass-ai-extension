"""Persistent chat session service."""

import uuid
import json
from typing import List, Optional, Dict, Any

from database.connection import db
from llm.adapter import llm_adapter
from llm.base import LLMMessage
from llm.prompts import SESSION_SUMMARY_PROMPT


class ChatService:
    """Manages persistent chat sessions and messages."""

    @staticmethod
    async def create_session(thread_id=None, page_url=None, page_title=None) -> str:
        session_id = str(uuid.uuid4())[:12]
        title = page_title or "新对话"
        await db.execute(
            """INSERT INTO chat_sessions (id, title, thread_id, page_url, page_title)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, title, thread_id, page_url, page_title)
        )
        return session_id

    @staticmethod
    async def add_message(session_id: str, role: str, content: str, tokens_used: int = 0) -> int:
        await db.execute(
            """INSERT INTO chat_messages (session_id, role, content, tokens_used)
               VALUES (?, ?, ?, ?)""",
            (session_id, role, content, tokens_used)
        )
        row = await db.fetchone("SELECT last_insert_rowid() as id")
        msg_id = row["id"]
        await db.execute(
            """UPDATE chat_sessions SET message_count = message_count + 1,
               updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')
               WHERE id = ?""",
            (session_id,)
        )
        return msg_id

    @staticmethod
    async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        session = await db.fetchone(
            "SELECT * FROM chat_sessions WHERE id = ?", (session_id,)
        )
        if not session:
            return None
        messages = await db.fetchall(
            "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at",
            (session_id,)
        )
        return {**dict(session), "messages": [dict(m) for m in messages]}

    @staticmethod
    async def get_recent_messages(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        rows = await db.fetchall(
            """SELECT * FROM chat_messages WHERE session_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (session_id, limit)
        )
        return [dict(r) for r in reversed(rows)]

    @staticmethod
    async def list_sessions(page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        total = await db.fetchval("SELECT COUNT(*) FROM chat_sessions")
        offset = (page - 1) * page_size
        rows = await db.fetchall(
            """SELECT * FROM chat_sessions ORDER BY updated_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, offset)
        )
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": [dict(r) for r in rows],
            "pagination": {
                "page": page, "page_size": page_size,
                "total": total, "total_pages": total_pages
            }
        }

    @staticmethod
    async def delete_session(session_id: str) -> bool:
        result = await db.execute(
            "DELETE FROM chat_sessions WHERE id = ?", (session_id,)
        )
        return result.rowcount > 0

    @staticmethod
    async def search_conversations(query: str, limit: int = 20) -> List[Dict[str, Any]]:
        words = query.strip().split()
        if not words:
            return []
        fts_query = " AND ".join(words)
        try:
            rows = await db.fetchall(
                """SELECT cm.id, cm.session_id, cm.role, cm.content, cm.created_at,
                          cs.title as session_title, cs.thread_id
                   FROM chat_messages_fts fts
                   JOIN chat_messages cm ON cm.rowid = fts.rowid
                   JOIN chat_sessions cs ON cs.id = cm.session_id
                   WHERE chat_messages_fts MATCH ?
                   ORDER BY rank LIMIT ?""",
                (fts_query, limit)
            )
            return [dict(r) for r in rows]
        except Exception:
            # Fallback to LIKE search
            like_pattern = f"%{query}%"
            rows = await db.fetchall(
                """SELECT cm.id, cm.session_id, cm.role, cm.content, cm.created_at,
                          cs.title as session_title, cs.thread_id
                   FROM chat_messages cm
                   JOIN chat_sessions cs ON cs.id = cm.session_id
                   WHERE cm.content LIKE ?
                   ORDER BY cm.created_at DESC LIMIT ?""",
                (like_pattern, limit)
            )
            return [dict(r) for r in rows]

    @staticmethod
    async def generate_session_summary(session_id: str) -> Optional[str]:
        messages = await db.fetchall(
            """SELECT role, content FROM chat_messages WHERE session_id = ?
               ORDER BY created_at LIMIT 20""",
            (session_id,)
        )
        if not messages:
            return None
        conversation = "\n".join(
            f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:200]}"
            for m in messages
        )
        try:
            llm = llm_adapter.get_llm()
            response = await llm.chat(
                [LLMMessage(role="user", content=SESSION_SUMMARY_PROMPT.format(conversation=conversation))],
                temperature=0.2, max_tokens=200
            )
            summary = response.content.strip()
            await db.execute(
                "UPDATE chat_sessions SET summary = ? WHERE id = ?",
                (summary, session_id)
            )
            return summary
        except Exception:
            return None


chat_service = ChatService()
