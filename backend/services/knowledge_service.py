"""Knowledge (bookmarks) management service."""

import json
import csv
import io
from datetime import datetime
from typing import List, Dict, Any, Optional

from database.connection import db
from services.tag_service import TagService
from services.md_storage import save_md, delete_md, resolve_content


class KnowledgeService:
    """Service for bookmark/knowledge management."""
    
    @staticmethod
    def _generate_id(thread_id: str) -> str:
        """Generate bookmark ID from thread_id."""
        import hashlib
        return hashlib.md5(thread_id.encode()).hexdigest()[:16]
    
    @staticmethod
    async def create_bookmark(
        thread_id: str,
        title: str,
        url: str,
        summary: Optional[str] = None,
        tags: List[str] = None
    ) -> Dict[str, Any]:
        """Create a new bookmark."""
        bookmark_id = KnowledgeService._generate_id(thread_id)
        tags = tags or []
        
        await db.execute(
            """INSERT INTO bookmarks (id, thread_id, title, url, summary)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(thread_id) DO UPDATE SET
               title = excluded.title,
               url = excluded.url,
               summary = excluded.summary,
               updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')""",
            (bookmark_id, thread_id, title, url, summary)
        )
        
        # Set tags
        if tags:
            await TagService.set_bookmark_tags(bookmark_id, tags)
        
        return await KnowledgeService.get_bookmark(bookmark_id)
    
    @staticmethod
    async def get_bookmark(bookmark_id: str) -> Optional[Dict[str, Any]]:
        """Get bookmark by ID."""
        row = await db.fetchone(
            "SELECT * FROM bookmarks WHERE id = ?",
            (bookmark_id,)
        )
        if not row:
            return None
        
        bookmark = dict(row)
        bookmark["bookmark_id"] = bookmark.pop("id")
        bookmark["tags"] = [t["name"] for t in await TagService.get_bookmark_tags(bookmark_id)]

        # Get notes — resolve file paths to actual content, but also
        # keep the raw stored value as `file_path` so the frontend's
        # "copy path" button can show the real location on disk.
        note_row = await db.fetchone(
            "SELECT * FROM notes WHERE bookmark_id = ?",
            (bookmark_id,)
        )
        if note_row:
            note = dict(note_row)
            raw = note.get("content") or ""
            # If the stored value looks like a relative path (starts with
            # "knowledge/"), expose it; otherwise it's inline text.
            if raw.startswith("knowledge/"):
                from config import get_data_dir
                note["file_path"] = str(get_data_dir() / raw)
            note["content"] = resolve_content(raw)
            bookmark["notes"] = note

        return bookmark
    
    @staticmethod
    async def get_bookmark_by_thread(thread_id: str) -> Optional[Dict[str, Any]]:
        """Get bookmark by thread_id."""
        row = await db.fetchone(
            "SELECT id FROM bookmarks WHERE thread_id = ?",
            (thread_id,)
        )
        if row:
            return await KnowledgeService.get_bookmark(row["id"])
        return None
    
    @staticmethod
    async def update_bookmark(
        bookmark_id: str,
        title: Optional[str] = None,
        url: Optional[str] = None,
        summary: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """Update bookmark."""
        # Build update fields
        updates = []
        params = []
        
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if url is not None:
            updates.append("url = ?")
            params.append(url)
        if summary is not None:
            updates.append("summary = ?")
            params.append(summary)
        
        if updates:
            updates.append("updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')")
            params.append(bookmark_id)
            
            await db.execute(
                f"UPDATE bookmarks SET {', '.join(updates)} WHERE id = ?",
                tuple(params)
            )
        
        # Update tags
        if tags is not None:
            await TagService.set_bookmark_tags(bookmark_id, tags)
        
        return await KnowledgeService.get_bookmark(bookmark_id)
    
    @staticmethod
    async def delete_bookmark(bookmark_id: str) -> bool:
        """Delete bookmark + associated MD files."""
        # Collect file paths before CASCADE deletes the DB rows
        note = await db.fetchone(
            "SELECT content FROM notes WHERE bookmark_id = ?", (bookmark_id,)
        )
        bm = await db.fetchone(
            "SELECT thread_id FROM bookmarks WHERE id = ?", (bookmark_id,)
        )

        result = await db.execute(
            "DELETE FROM bookmarks WHERE id = ?",
            (bookmark_id,)
        )

        if result.rowcount > 0:
            # Clean up MD files
            if note:
                delete_md(note["content"])  # no-op if inline text
            if bm:
                # Also try to delete the summary file for this thread
                delete_md(f"knowledge/posts/{bm['thread_id']}.md")
            return True
        return False
    
    @staticmethod
    async def list_bookmarks(
        tag: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "created",
        sort_order: str = "desc",
        page: int = 1,
        page_size: int = 20
    ) -> Dict[str, Any]:
        """List bookmarks with filtering and pagination."""
        offset = (page - 1) * page_size
        
        # Build query
        where_clauses = []
        params = []
        
        if tag:
            where_clauses.append("""
                EXISTS (
                    SELECT 1 FROM bookmark_tags bt 
                    JOIN tags t ON bt.tag_id = t.id 
                    WHERE bt.bookmark_id = b.id AND t.name = ?
                )
            """)
            params.append(tag)
        
        if search:
            where_clauses.append("(b.title LIKE ? OR b.summary LIKE ?)")
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])
        
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        
        # Sort
        sort_column = {
            "created": "b.created_at",
            "updated": "b.updated_at",
            "title": "b.title"
        }.get(sort_by, "b.created_at")
        
        sort_dir = "DESC" if sort_order == "desc" else "ASC"
        
        # Count
        count_sql = f"SELECT COUNT(*) FROM bookmarks b {where_sql}"
        total = await db.fetchval(count_sql, tuple(params))
        
        # Fetch
        query = f"""
            SELECT b.* FROM bookmarks b
            {where_sql}
            ORDER BY {sort_column} {sort_dir}
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])
        
        rows = await db.fetchall(query, tuple(params))
        
        items = []
        for row in rows:
            item = dict(row)
            item["bookmark_id"] = item.pop("id")
            item["tags"] = [t["name"] for t in await TagService.get_bookmark_tags(item["bookmark_id"])]
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
    
    @staticmethod
    async def add_note(bookmark_id: str, content: str) -> Dict[str, Any]:
        """Add or update note for bookmark. Content is stored as a MD file."""
        # Get the thread_id for the filename
        bm = await db.fetchone(
            "SELECT thread_id FROM bookmarks WHERE id = ?", (bookmark_id,)
        )
        if not bm:
            return None
        thread_id = bm["thread_id"]

        # Write to MD file; DB stores the relative path
        content_path = save_md("posts", thread_id, content)

        # Check if note exists
        existing = await db.fetchone(
            "SELECT id FROM notes WHERE bookmark_id = ?",
            (bookmark_id,)
        )

        if existing:
            await db.execute(
                """UPDATE notes SET content = ?,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%S+08:00', 'now', '+8 hours')
                   WHERE bookmark_id = ?""",
                (content_path, bookmark_id)
            )
            note_id = existing["id"]
        else:
            cursor = await db.execute(
                "INSERT INTO notes (bookmark_id, content) VALUES (?, ?)",
                (bookmark_id, content_path)
            )
            note_id = cursor.lastrowid

        row = await db.fetchone("SELECT * FROM notes WHERE id = ?", (note_id,))
        result = dict(row)
        result["content"] = resolve_content(result.get("content"))
        return result
    
    @staticmethod
    async def get_note(bookmark_id: str) -> Optional[Dict[str, Any]]:
        """Get note for bookmark. Resolves file paths to actual content."""
        row = await db.fetchone(
            "SELECT * FROM notes WHERE bookmark_id = ?",
            (bookmark_id,)
        )
        if row:
            result = dict(row)
            result["content"] = resolve_content(result.get("content"))
            return result
        return None
    
    @staticmethod
    async def export_bookmarks(format: str = "json") -> str:
        """Export bookmarks to various formats."""
        rows = await db.fetchall(
            """SELECT b.*, GROUP_CONCAT(t.name) as tag_names
               FROM bookmarks b
               LEFT JOIN bookmark_tags bt ON b.id = bt.bookmark_id
               LEFT JOIN tags t ON bt.tag_id = t.id
               GROUP BY b.id
               ORDER BY b.created_at DESC"""
        )
        
        # Convert all rows to dicts first
        items = [dict(row) for row in rows]
        for item in items:
            tag_names = item.pop("tag_names", None)
            item["tags"] = tag_names.split(",") if tag_names else []

        if format == "json":
            return json.dumps(items, ensure_ascii=False, indent=2)

        elif format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Thread ID", "Title", "URL", "Summary", "Tags", "Created", "Updated"])

            for item in items:
                writer.writerow([
                    item["id"],
                    item["thread_id"],
                    item["title"],
                    item["url"],
                    item.get("summary") or "",
                    ",".join(item["tags"]),
                    item["created_at"],
                    item["updated_at"]
                ])

            return output.getvalue()

        elif format == "markdown":
            lines = ["# QuantClass Bookmarks\n"]

            for item in items:
                tag_str = " ".join([f"`{t}`" for t in item["tags"]]) if item["tags"] else ""

                lines.append(f"## {item['title']}")
                lines.append(f"- **URL:** {item['url']}")
                lines.append(f"- **Tags:** {tag_str}")
                lines.append(f"- **Created:** {item['created_at']}")
                if item.get("summary"):
                    lines.append(f"\n{item['summary']}\n")
                lines.append("")

            return "\n".join(lines)
        
        else:
            raise ValueError(f"Unsupported format: {format}")
