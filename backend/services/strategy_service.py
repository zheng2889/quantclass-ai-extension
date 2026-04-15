"""Strategy entity extraction service."""

import json
import logging
from typing import List, Optional, Dict, Any

from database.connection import db
from llm.adapter import llm_adapter
from llm.base import LLMMessage
from llm.prompts import STRATEGY_EXTRACT_PROMPT

logger = logging.getLogger(__name__)


class StrategyService:
    """Extracts and manages structured strategy entities from forum posts."""

    @staticmethod
    async def extract_from_content(thread_id: str, title: str, content: str) -> Optional[Dict[str, Any]]:
        """Extract strategy entity from post content using LLM."""
        # Truncate content for LLM
        if len(content) > 6000:
            content = content[:3000] + "\n...\n" + content[-2000:]

        try:
            llm = llm_adapter.get_llm()
            response = await llm.chat(
                [LLMMessage(role="user", content=STRATEGY_EXTRACT_PROMPT.format(
                    title=title, content=content
                ))],
                temperature=0.2, max_tokens=1000
            )

            text = response.content.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            data = json.loads(text)

            # Skip if no strategy found
            if not data.get("name") or data.get("confidence", 0) < 0.3:
                return None

            name = data.pop("name")
            strategy_type = data.pop("strategy_type", "other")
            asset_class = data.pop("asset_class", None)
            confidence = data.pop("confidence", 0.7)

            await db.execute(
                """INSERT INTO strategy_entities
                   (thread_id, name, strategy_type, asset_class, structured_data, model_used, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(thread_id, name) DO UPDATE SET
                       strategy_type = excluded.strategy_type,
                       asset_class = excluded.asset_class,
                       structured_data = excluded.structured_data,
                       model_used = excluded.model_used,
                       confidence = excluded.confidence,
                       updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')""",
                (thread_id, name, strategy_type, asset_class,
                 json.dumps(data, ensure_ascii=False), response.model, confidence)
            )

            return {
                "thread_id": thread_id,
                "name": name,
                "strategy_type": strategy_type,
                "asset_class": asset_class,
                "structured_data": data,
                "confidence": confidence
            }
        except Exception as e:
            logger.warning(f"Strategy extraction failed for thread {thread_id}: {e}")
            return None

    @staticmethod
    async def get_strategies_for_thread(thread_id: str) -> List[Dict[str, Any]]:
        rows = await db.fetchall(
            "SELECT * FROM strategy_entities WHERE thread_id = ? ORDER BY confidence DESC",
            (thread_id,)
        )
        results = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"]) if d["structured_data"] else {}
            results.append(d)
        return results

    @staticmethod
    async def list_strategies(strategy_type: str = None, asset_class: str = None,
                               page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        conditions = []
        params = []
        if strategy_type:
            conditions.append("strategy_type = ?")
            params.append(strategy_type)
        if asset_class:
            conditions.append("asset_class = ?")
            params.append(asset_class)

        where = "WHERE " + " AND ".join(conditions) if conditions else ""

        total = await db.fetchval(f"SELECT COUNT(*) FROM strategy_entities {where}", params)
        offset = (page - 1) * page_size
        rows = await db.fetchall(
            f"""SELECT * FROM strategy_entities {where}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [page_size, offset]
        )

        items = []
        for r in rows:
            d = dict(r)
            d["structured_data"] = json.loads(d["structured_data"]) if d["structured_data"] else {}
            items.append(d)

        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "items": items,
            "pagination": {
                "page": page, "page_size": page_size,
                "total": total, "total_pages": total_pages
            }
        }


strategy_service = StrategyService()
