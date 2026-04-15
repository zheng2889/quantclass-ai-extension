"""Search service using SQLite FTS5."""

import json
from typing import List, Dict, Any, Optional
from database.connection import db
from services.tag_service import TagService


class SearchService:
    """Full-text search service using SQLite FTS5."""

    @staticmethod
    def _normalize_scores(results: List[Dict[str, Any]]) -> None:
        """Rescale raw FTS5 ranks into a 0..1 relevance score in-place.

        Input assumption: each row has ``score`` set to either:
        - A negative float (FTS5 BM25 rank; more negative = better), or
        - 0 (LIKE fallback rows — no real ranking available).

        Output: each row's ``score`` is replaced with a float in [0, 1]
        where 1.0 is the best hit in this result set. LIKE-fallback rows
        default to 0.5 so they don't look like zero-confidence matches.
        """
        if not results:
            return

        fts_rows = [r for r in results if r.get("score") and r["score"] < 0]

        if not fts_rows:
            # All results came from the LIKE fallback. Give them a mid-tier
            # score so the UI progress bar is visible but not pegged.
            for row in results:
                row["score"] = 0.5
            return

        # All FTS rows have negative ranks. "Best" is the most negative.
        best = min(r["score"] for r in fts_rows)   # e.g. -0.002
        worst = max(r["score"] for r in fts_rows)  # e.g. -0.0005
        # Linear rescale:  best → 1.0,  worst → 0.0
        #   normalized = (raw - worst) / (best - worst)
        # (best - worst) is negative, (raw - worst) is negative for hits in
        # between, so the quotient lands in [0, 1].
        denom = best - worst

        for row in results:
            raw = row.get("score") or 0
            if raw >= 0:
                # LIKE fallback row mixed in with FTS hits — rare, but keep
                # it visible.
                row["score"] = 0.5
                continue
            if denom == 0:
                # Single FTS hit (or all hits tied): full bar.
                row["score"] = 1.0
            else:
                # Clamp to [0, 1] to scrub any -0 or floating-point drift.
                normalized = (raw - worst) / denom
                row["score"] = round(max(0.0, min(1.0, normalized)), 4)

    @staticmethod
    async def search(
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """Search bookmarks using FTS5."""
        offset = (page - 1) * page_size
        filters = filters or {}
        
        # Build FTS query
        # Support basic query syntax: word1 word2 -> word1 AND word2
        fts_query = " AND ".join(query.split())
        
        _like = f"%{query}%"
        rows = []
        total = 0
        try:
            # FTS5 search (best for space-separated keywords)
            rows = await db.fetchall(
                """SELECT
                    b.id,
                    b.thread_id,
                    b.title,
                    b.url,
                    b.summary,
                    b.created_at,
                    b.updated_at,
                    highlight(bookmarks_fts, 0, '<mark>', '</mark>') as title_highlight,
                    highlight(bookmarks_fts, 1, '<mark>', '</mark>') as summary_highlight,
                    rank
                   FROM bookmarks_fts
                   JOIN bookmarks b ON bookmarks_fts.rowid = b.rowid
                   WHERE bookmarks_fts MATCH ?
                   ORDER BY rank
                   LIMIT ? OFFSET ?""",
                (fts_query, page_size, offset)
            )
            if rows:
                total = await db.fetchval(
                    "SELECT COUNT(*) FROM bookmarks_fts WHERE bookmarks_fts MATCH ?",
                    (fts_query,)
                ) or 0
        except Exception:
            pass

        # Fallback: LIKE search — handles Chinese text (no tokenizer spaces) and FTS misses
        if not rows:
            rows = await db.fetchall(
                """SELECT
                    b.id,
                    b.thread_id,
                    b.title,
                    b.url,
                    b.summary,
                    b.created_at,
                    b.updated_at,
                    b.title as title_highlight,
                    b.summary as summary_highlight,
                    0 as rank
                   FROM bookmarks b
                   WHERE b.title LIKE ? OR b.summary LIKE ?
                   ORDER BY b.created_at DESC
                   LIMIT ? OFFSET ?""",
                (_like, _like, page_size, offset)
            )
            total = await db.fetchval(
                "SELECT COUNT(*) FROM bookmarks WHERE title LIKE ? OR summary LIKE ?",
                (_like, _like)
            ) or 0
        
        # Enrich results with tags
        results = []
        for row in rows:
            item = dict(row)
            item["tags"] = [t["name"] for t in await TagService.get_bookmark_tags(item["id"])]

            # Use highlighted version if available
            if item.get("title_highlight"):
                item["highlight"] = item["title_highlight"]
                if item.get("summary_highlight"):
                    item["highlight"] += " - " + item["summary_highlight"][:200]

            # Clean up internal fields
            item.pop("title_highlight", None)
            item.pop("summary_highlight", None)

            # Align field names with API spec
            item["bookmark_id"] = item.pop("id")
            item["score"] = item.pop("rank")

            results.append(item)

        # Normalize scores into a 0..1 range relative to the current result set.
        # FTS5's `rank` column is BM25 expressed as a negative float (more
        # negative = better, values live around -1e-6). The raw number is
        # useless for UI display, so we rescale it within this query's
        # results: the best (most negative) hit becomes 1.0, the worst tends
        # toward 0.0. LIKE-fallback rows have rank=0 and get a flat 0.5 so
        # the progress bar is still visible without implying a confidence
        # we don't actually have.
        SearchService._normalize_scores(results)
        
        total_pages = (total + page_size - 1) // page_size
        
        # Generate suggestions (simple approach)
        suggestions = await SearchService._generate_suggestions(query)
        
        return {
            "query": query,
            "results": results,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            },
            "suggestions": suggestions
        }
    
    @staticmethod
    async def _generate_suggestions(query: str) -> List[str]:
        """Generate search suggestions based on query."""
        # Get popular tags that match the query
        rows = await db.fetchall(
            "SELECT name FROM tags WHERE name LIKE ? ORDER BY name LIMIT 5",
            (f"%{query}%",)
        )
        
        suggestions = [row["name"] for row in rows]
        
        # Add some common variations
        words = query.split()
        if len(words) > 1:
            suggestions.insert(0, " ".join(words[:2]))
        
        return suggestions[:5]
    
    @staticmethod
    async def advanced_search(
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """Advanced search with multiple filters."""
        offset = (page - 1) * page_size
        
        where_clauses = []
        params = []
        
        if title:
            where_clauses.append("b.title LIKE ?")
            params.append(f"%{title}%")
        
        if content:
            where_clauses.append("(b.summary LIKE ? OR b.title LIKE ?)")
            params.extend([f"%{content}%", f"%{content}%"])
        
        if date_from:
            where_clauses.append("b.created_at >= ?")
            params.append(date_from)
        
        if date_to:
            where_clauses.append("b.created_at <= ?")
            params.append(date_to)
        
        if tags:
            tag_placeholders = ", ".join(["?"] * len(tags))
            where_clauses.append(f"""
                EXISTS (
                    SELECT 1 FROM bookmark_tags bt 
                    JOIN tags t ON bt.tag_id = t.id 
                    WHERE bt.bookmark_id = b.id AND t.name IN ({tag_placeholders})
                )
            """)
            params.extend(tags)
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        # Count
        count_sql = f"SELECT COUNT(*) FROM bookmarks b {where_sql}"
        total = await db.fetchval(count_sql, tuple(params)) or 0
        
        # Fetch
        query_sql = f"""
            SELECT b.* FROM bookmarks b
            {where_sql}
            ORDER BY b.created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])
        
        rows = await db.fetchall(query_sql, tuple(params))
        
        items = []
        for row in rows:
            item = dict(row)
            item["tags"] = [t["name"] for t in await TagService.get_bookmark_tags(item["id"])]
            item["bookmark_id"] = item.pop("id")
            items.append(item)
        
        total_pages = (total + page_size - 1) // page_size
        
        return {
            "query": {
                "title": title,
                "content": content,
                "tags": tags,
                "date_from": date_from,
                "date_to": date_to
            },
            "results": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }
    
    @staticmethod
    async def reindex() -> Dict[str, Any]:
        """Rebuild FTS index."""
        try:
            # Rebuild FTS index
            await db.execute("INSERT INTO bookmarks_fts(bookmarks_fts) VALUES ('rebuild')")
            
            # Get stats
            count = await db.fetchval("SELECT COUNT(*) FROM bookmarks_fts")
            
            return {
                "success": True,
                "message": "FTS index rebuilt successfully",
                "indexed_count": count
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to rebuild index: {str(e)}",
                "indexed_count": 0
            }
