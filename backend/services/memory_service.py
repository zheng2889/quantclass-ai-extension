"""Memory management service — user profile, memory items, context building."""

import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from database.connection import db
from llm.adapter import llm_adapter
from llm.base import LLMMessage
from llm.prompts import MEMORY_EXTRACT_PROMPT, PROFILE_INFER_PROMPT

logger = logging.getLogger(__name__)


class MemoryService:
    """Manages user profile, memory items, and context injection."""

    # ── User Profile ──

    @staticmethod
    async def get_user_profile(user_id: str = "default") -> List[Dict[str, Any]]:
        rows = await db.fetchall(
            "SELECT * FROM user_profile WHERE user_id = ? ORDER BY profile_key",
            (user_id,)
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def set_profile_item(profile_key: str, profile_value: str,
                                source: str = "manual", confidence: float = 0.8,
                                user_id: str = "default") -> None:
        await db.execute(
            """INSERT INTO user_profile (user_id, profile_key, profile_value, source, confidence)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, profile_key) DO UPDATE SET
                   profile_value = excluded.profile_value,
                   source = excluded.source,
                   confidence = excluded.confidence,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')""",
            (user_id, profile_key, profile_value, source, confidence)
        )

    # ── Memory Items ──

    @staticmethod
    async def get_active_memories(limit: int = 20) -> List[Dict[str, Any]]:
        rows = await db.fetchall(
            """SELECT * FROM memory_items WHERE is_active = 1
               ORDER BY importance DESC, access_count DESC LIMIT ?""",
            (limit,)
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def add_memory(memory_type: str, content: str, importance: int = 3,
                          source_session_id: str = None,
                          source_thread_id: str = None) -> int:
        # Deduplicate: skip if very similar memory already exists
        existing = await db.fetchall(
            "SELECT id, content FROM memory_items WHERE memory_type = ? AND is_active = 1",
            (memory_type,)
        )
        for row in existing:
            if row["content"] == content:
                return row["id"]

        await db.execute(
            """INSERT INTO memory_items
               (memory_type, content, importance, source_session_id, source_thread_id)
               VALUES (?, ?, ?, ?, ?)""",
            (memory_type, content, importance, source_session_id, source_thread_id)
        )
        row = await db.fetchone("SELECT last_insert_rowid() as id")
        return row["id"]

    @staticmethod
    async def list_memories(include_inactive: bool = False) -> List[Dict[str, Any]]:
        if include_inactive:
            rows = await db.fetchall(
                "SELECT * FROM memory_items ORDER BY importance DESC, created_at DESC"
            )
        else:
            rows = await db.fetchall(
                """SELECT * FROM memory_items WHERE is_active = 1
                   ORDER BY importance DESC, created_at DESC"""
            )
        return [dict(r) for r in rows]

    @staticmethod
    async def deactivate_memory(memory_id: int) -> bool:
        result = await db.execute(
            "UPDATE memory_items SET is_active = 0 WHERE id = ?", (memory_id,)
        )
        return result.rowcount > 0

    @staticmethod
    async def delete_memory(memory_id: int) -> bool:
        result = await db.execute(
            "DELETE FROM memory_items WHERE id = ?", (memory_id,)
        )
        return result.rowcount > 0

    # ── Context Building ──

    @staticmethod
    async def build_memory_context(thread_id: str = None, max_tokens: int = 1500) -> str:
        """Build memory context string to inject into LLM system prompt."""
        sections = []
        char_budget = max_tokens * 3  # rough chars-to-tokens ratio for Chinese

        # 1. User profile
        profile = await MemoryService.get_user_profile()
        if profile:
            profile_lines = []
            for item in profile:
                profile_lines.append(f"- {item['profile_key']}: {item['profile_value']}")
            sections.append("## 用户画像\n" + "\n".join(profile_lines))

        # 2. Active memories
        memories = await MemoryService.get_active_memories(limit=15)
        if memories:
            mem_lines = []
            for m in memories:
                mem_lines.append(f"- [{m['memory_type']}] {m['content']}")
            sections.append("## 重要记忆\n" + "\n".join(mem_lines))

            # Update access counts
            ids = [m["id"] for m in memories]
            placeholders = ",".join("?" * len(ids))
            await db.execute(
                f"""UPDATE memory_items SET access_count = access_count + 1,
                    last_accessed_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')
                    WHERE id IN ({placeholders})""",
                ids
            )

        # 3. Related strategies (if thread_id provided)
        if thread_id:
            strategies = await db.fetchall(
                "SELECT name, strategy_type, structured_data FROM strategy_entities WHERE thread_id = ?",
                (thread_id,)
            )
            if strategies:
                strat_lines = []
                for s in strategies:
                    data = json.loads(s["structured_data"]) if s["structured_data"] else {}
                    key_logic = data.get("key_logic", "")
                    strat_lines.append(f"- {s['name']} ({s['strategy_type']}): {key_logic}")
                sections.append("## 当前帖子相关策略\n" + "\n".join(strat_lines))

        context = "\n\n".join(sections)
        if len(context) > char_budget:
            context = context[:char_budget] + "\n..."
        return context

    # ── Memory Extraction ──

    @staticmethod
    async def extract_memories_from_conversation(session_id: str) -> List[Dict]:
        """Extract memories from a conversation using LLM. Run as background task."""
        try:
            messages = await db.fetchall(
                """SELECT role, content FROM chat_messages WHERE session_id = ?
                   ORDER BY created_at LIMIT 20""",
                (session_id,)
            )
            if len(messages) < 2:
                return []

            conversation = "\n".join(
                f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content'][:300]}"
                for m in messages
            )

            llm = llm_adapter.get_llm()
            response = await llm.chat(
                [LLMMessage(role="user", content=MEMORY_EXTRACT_PROMPT.format(conversation=conversation))],
                temperature=0.2, max_tokens=500
            )

            # Parse JSON from response
            text = response.content.strip()
            # Handle markdown code blocks
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            extracted = json.loads(text)
            results = []
            for item in extracted[:3]:
                mem_id = await MemoryService.add_memory(
                    memory_type=item.get("memory_type", "user_fact"),
                    content=item.get("content", ""),
                    importance=item.get("importance", 3),
                    source_session_id=session_id,
                )
                results.append({"id": mem_id, **item})
            return results
        except Exception as e:
            logger.warning(f"Memory extraction failed: {e}")
            return []

    @staticmethod
    async def infer_user_profile() -> None:
        """Infer user profile from interaction history. Run at most once per day."""
        try:
            # Check last update
            profile = await MemoryService.get_user_profile()
            existing_str = json.dumps({p["profile_key"]: p["profile_value"] for p in profile},
                                       ensure_ascii=False) if profile else "{}"

            # Get recent reads
            reads = await db.fetchall(
                "SELECT title FROM reading_history ORDER BY created_at DESC LIMIT 20"
            )
            recent_reads = "\n".join(f"- {r['title']}" for r in reads) if reads else "无"

            # Get recent chat topics
            sessions = await db.fetchall(
                "SELECT title, summary FROM chat_sessions ORDER BY updated_at DESC LIMIT 10"
            )
            recent_topics = "\n".join(
                f"- {s['title']}: {s['summary'] or '无摘要'}" for s in sessions
            ) if sessions else "无"

            # Get tag distribution
            tags = await db.fetchall(
                """SELECT t.name, COUNT(*) as cnt FROM bookmark_tags bt
                   JOIN tags t ON t.id = bt.tag_id
                   GROUP BY t.name ORDER BY cnt DESC LIMIT 10"""
            )
            tag_dist = ", ".join(f"{t['name']}({t['cnt']})" for t in tags) if tags else "无"

            llm = llm_adapter.get_llm()
            response = await llm.chat(
                [LLMMessage(role="user", content=PROFILE_INFER_PROMPT.format(
                    recent_reads=recent_reads,
                    recent_topics=recent_topics,
                    tag_distribution=tag_dist,
                    existing_profile=existing_str
                ))],
                temperature=0.2, max_tokens=500
            )

            text = response.content.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            inferred = json.loads(text)
            for key, value in inferred.items():
                if value:
                    val_str = json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else str(value)
                    await MemoryService.set_profile_item(key, val_str, source="auto", confidence=0.7)
        except Exception as e:
            logger.warning(f"Profile inference failed: {e}")


memory_service = MemoryService()
