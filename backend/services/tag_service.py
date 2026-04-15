"""Tag management service."""

from typing import List, Dict, Any, Optional
from database.connection import db


class TagService:
    """Service for tag management."""
    
    @staticmethod
    async def list_tags(category: Optional[str] = None) -> Dict[str, Any]:
        """List all tags, optionally filtered by category."""
        if category:
            rows = await db.fetchall(
                "SELECT * FROM tags WHERE category = ? ORDER BY name",
                (category,)
            )
        else:
            rows = await db.fetchall(
                "SELECT * FROM tags ORDER BY category, name"
            )
        
        items = [dict(row) for row in rows]
        
        # Group by category
        categories: Dict[str, List[str]] = {}
        for item in items:
            cat = item["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item["name"])
        
        return {
            "items": items,
            "categories": categories
        }
    
    @staticmethod
    async def get_tag(tag_id: int) -> Optional[Dict[str, Any]]:
        """Get tag by ID."""
        row = await db.fetchone(
            "SELECT * FROM tags WHERE id = ?",
            (tag_id,)
        )
        if row:
            return dict(row)
        return None
    
    @staticmethod
    async def get_tag_by_name(name: str) -> Optional[Dict[str, Any]]:
        """Get tag by name."""
        row = await db.fetchone(
            "SELECT * FROM tags WHERE name = ?",
            (name,)
        )
        if row:
            return dict(row)
        return None
    
    @staticmethod
    async def create_tag(name: str, category: str = "custom") -> Dict[str, Any]:
        """Create a new tag."""
        # Check if exists
        existing = await TagService.get_tag_by_name(name)
        if existing:
            return existing
        
        cursor = await db.execute(
            "INSERT INTO tags (name, category) VALUES (?, ?)",
            (name, category)
        )
        
        return {
            "id": cursor.lastrowid,
            "name": name,
            "category": category
        }
    
    @staticmethod
    async def delete_tag(tag_id: int) -> bool:
        """Delete a tag."""
        result = await db.execute(
            "DELETE FROM tags WHERE id = ?",
            (tag_id,)
        )
        return result.rowcount > 0
    
    @staticmethod
    async def suggest_tags(
        content: str,
        existing_tags: List[str] = None,
        max_suggestions: int = 5
    ) -> List[Dict[str, Any]]:
        """Suggest tags based on content using LLM."""
        from llm.adapter import llm_adapter
        from llm.prompts import get_prompt, TAG_SUGGESTION_PROMPT
        from llm.base import LLMMessage

        existing_tags = existing_tags or []

        # Get available tags for context
        all_tags = await TagService.list_tags()
        available_tags = [t["name"] for t in all_tags["items"]]

        llm = llm_adapter.get_llm()

        prompt = get_prompt(
            TAG_SUGGESTION_PROMPT,
            content=content[:4000],
            existing_tags=", ".join(existing_tags),
            max_suggestions=max_suggestions
        )
        messages = [LLMMessage(role="user", content=prompt)]

        try:
            response = await llm.chat(messages, temperature=0.3)

            # Parse suggestions
            suggestions = []
            raw_tags = [t.strip() for t in response.content.split(",") if t.strip()]
            for i, tag in enumerate(raw_tags):
                if tag and tag not in existing_tags:
                    confidence = round(max(0.5, 0.95 - i * 0.05), 2)
                    category = TagService._infer_tag_category(tag)
                    suggestions.append({
                        "name": tag,
                        "category": category,
                        "confidence": confidence
                    })

            return suggestions[:max_suggestions]
        except Exception:
            # Fallback: return most relevant system tags
            system_tags = all_tags.get("categories", {}).get("system", [])[:max_suggestions]
            return [
                {"name": t, "category": "system", "confidence": 0.6}
                for t in system_tags if t not in existing_tags
            ]

    @staticmethod
    def _infer_tag_category(tag_name: str) -> str:
        """Infer tag category from name patterns."""
        strategy_keywords = ["策略", "回归", "趋势", "动量", "套利", "对冲"]
        asset_keywords = ["A股", "期货", "期权", "债券", "美股", "加密"]
        difficulty_keywords = ["入门", "进阶", "高级", "专家"]

        for kw in strategy_keywords:
            if kw in tag_name:
                return "strategy_type"
        for kw in asset_keywords:
            if kw in tag_name:
                return "asset_class"
        for kw in difficulty_keywords:
            if kw in tag_name:
                return "difficulty"
        return "custom"
    
    @staticmethod
    async def get_bookmark_tags(bookmark_id: str) -> List[Dict[str, Any]]:
        """Get tags for a bookmark."""
        rows = await db.fetchall(
            """SELECT t.* FROM tags t
               JOIN bookmark_tags bt ON t.id = bt.tag_id
               WHERE bt.bookmark_id = ?
               ORDER BY t.name""",
            (bookmark_id,)
        )
        return [dict(row) for row in rows]
    
    @staticmethod
    async def set_bookmark_tags(bookmark_id: str, tag_names: List[str]) -> None:
        """Set tags for a bookmark (replaces existing)."""
        # Remove existing tags
        await db.execute(
            "DELETE FROM bookmark_tags WHERE bookmark_id = ?",
            (bookmark_id,)
        )
        
        # Add new tags
        for tag_name in tag_names:
            # Ensure tag exists
            tag = await TagService.get_tag_by_name(tag_name)
            if not tag:
                tag = await TagService.create_tag(tag_name)
            
            await db.execute(
                "INSERT OR IGNORE INTO bookmark_tags (bookmark_id, tag_id) VALUES (?, ?)",
                (bookmark_id, tag["id"])
            )
