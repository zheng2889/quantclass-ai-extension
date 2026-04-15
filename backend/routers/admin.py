"""Admin router - system administration."""

import os
from pathlib import Path
from fastapi import APIRouter, Depends
from models import success, error, ResponseCode
from database.connection import db
from services import SearchService
from routers.auth import require_admin

router = APIRouter(tags=["Admin"])


@router.get("/stats")
async def get_stats(admin: dict = Depends(require_admin)):
    """Get system statistics."""
    try:
        # Database stats
        db_stats = {
            "bookmarks": await db.fetchval("SELECT COUNT(*) FROM bookmarks") or 0,
            "summaries": await db.fetchval("SELECT COUNT(*) FROM summaries") or 0,
            "tags": await db.fetchval("SELECT COUNT(*) FROM tags") or 0,
            "notes": await db.fetchval("SELECT COUNT(*) FROM notes") or 0,
        }
        
        # LLM usage stats
        llm_stats = await db.fetchone("""
            SELECT 
                COUNT(*) as total_calls,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens,
                AVG(latency_ms) as avg_latency
            FROM llm_logs
            WHERE created_at > datetime('now', '-7 days')
        """)
        
        llm_usage = dict(llm_stats) if llm_stats else {
            "total_calls": 0,
            "successful_calls": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "avg_latency": 0
        }
        
        # Storage stats
        from config import get_database_path, get_data_dir
        db_path = get_database_path()
        data_dir = get_data_dir()
        
        storage_stats = {
            "database_size_mb": 0,
            "data_dir_size_mb": 0
        }
        
        if db_path.exists():
            storage_stats["database_size_mb"] = round(db_path.stat().st_size / (1024 * 1024), 2)
        
        if data_dir.exists():
            total_size = sum(
                f.stat().st_size for f in data_dir.rglob("*") if f.is_file()
            )
            storage_stats["data_dir_size_mb"] = round(total_size / (1024 * 1024), 2)
        
        # Config info
        from config import load_config
        config = load_config()
        
        return success({
            "database": db_stats,
            "llm_usage": llm_usage,
            "storage": storage_stats,
            "config": {
                "default_model": config.default_model,
                "default_provider": config.default_provider,
                "available_providers": list(config.providers.keys())
            }
        })
    except Exception as e:
        return error(ResponseCode.DB_ERROR, str(e))


@router.post("/reindex")
async def reindex(force: bool = False, admin: dict = Depends(require_admin)):
    """Rebuild FTS search index."""
    try:
        result = await SearchService.reindex()
        if result["success"]:
            return success(result)
        return error(ResponseCode.DB_ERROR, result["message"])
    except Exception as e:
        return error(ResponseCode.DB_ERROR, str(e))


@router.get("/logs/llm")
async def get_llm_logs(limit: int = 100, admin: dict = Depends(require_admin)):
    """Get recent LLM API logs."""
    try:
        rows = await db.fetchall(
            """SELECT * FROM llm_logs 
               ORDER BY created_at DESC 
               LIMIT ?""",
            (limit,)
        )
        return success({
            "logs": [dict(row) for row in rows],
            "count": len(rows)
        })
    except Exception as e:
        return error(ResponseCode.DB_ERROR, str(e))
