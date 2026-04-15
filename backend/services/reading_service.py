"""Reading history tracking service."""

from typing import List, Dict, Any

from database.connection import db


class ReadingService:
    """Tracks user reading behavior on forum posts."""

    @staticmethod
    async def record_visit(thread_id: str, title: str, url: str,
                            duration_seconds: int = 0,
                            scroll_depth: float = 0.0) -> int:
        await db.execute(
            """INSERT INTO reading_history
               (thread_id, title, url, duration_seconds, scroll_depth)
               VALUES (?, ?, ?, ?, ?)""",
            (thread_id, title, url, duration_seconds, scroll_depth)
        )
        row = await db.fetchone("SELECT last_insert_rowid() as id")
        return row["id"]

    @staticmethod
    async def get_recent_reads(limit: int = 20) -> List[Dict[str, Any]]:
        rows = await db.fetchall(
            "SELECT * FROM reading_history ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in rows]

    @staticmethod
    async def get_reading_stats() -> Dict[str, Any]:
        total = await db.fetchval("SELECT COUNT(*) FROM reading_history")
        unique_threads = await db.fetchval("SELECT COUNT(DISTINCT thread_id) FROM reading_history")
        avg_duration = await db.fetchval(
            "SELECT COALESCE(AVG(duration_seconds), 0) FROM reading_history WHERE duration_seconds > 0"
        )
        avg_scroll = await db.fetchval(
            "SELECT COALESCE(AVG(scroll_depth), 0) FROM reading_history WHERE scroll_depth > 0"
        )

        # Top read threads
        top_threads = await db.fetchall(
            """SELECT thread_id, title, COUNT(*) as visit_count,
                      SUM(duration_seconds) as total_duration
               FROM reading_history
               GROUP BY thread_id ORDER BY visit_count DESC LIMIT 10"""
        )

        return {
            "total_reads": total,
            "unique_threads": unique_threads,
            "avg_duration_seconds": round(avg_duration, 1),
            "avg_scroll_depth": round(avg_scroll, 2),
            "top_threads": [dict(r) for r in top_threads]
        }


reading_service = ReadingService()
