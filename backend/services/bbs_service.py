"""BBS Service."""

import logging
import random
from typing import Optional
from database.connection import db
from services.md_storage import save_md, resolve_content
from services.strategy_service import StrategyService
from llm.adapter import llm_adapter
from llm.prompts import get_prompt
from llm.base import LLMMessage

logger = logging.getLogger(__name__)

BBS_ANALYSIS_PROMPT = """你是一位量化金融领域的专业分析师。请对以下论坛帖子进行深度分析。

标题：{title}
作者：{author}

帖子正文：
{content}

请用中文回复，输出格式为 Markdown，包含：
1. **核心观点**（2-3 句话概括主旨）
2. **策略要点**（提取可交易的策略思路、因子、信号）
3. **风险提示**（可能的风险和局限性）
4. **适用场景**（对什么类型的交易者最有价值）

分析结果："""


class BBSService:
    """BBS service for managing posts."""

    @staticmethod
    async def sync_post(
        post_id: str,
        url: str,
        title: Optional[str] = None,
        author_id: Optional[str] = None,
        author_name: Optional[str] = None,
        status: str = "pending"
    ) -> dict:
        """Insert or update a post using UPSERT (atomic, no race condition)."""
        await db.execute(
            """INSERT INTO bbs_list (post_id, url, title, author_id, author_name, status)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(post_id) DO UPDATE SET
                url = excluded.url,
                title = excluded.title,
                author_id = excluded.author_id,
                author_name = excluded.author_name,
                status = excluded.status""",
            (post_id, url, title, author_id, author_name, status)
        )

        row = await db.fetchone(
            "SELECT id FROM bbs_list WHERE post_id = ?",
            (post_id,)
        )
        return {"id": row["id"], "post_id": post_id, "action": "synced"}

    @staticmethod
    async def list_posts(
        publish_start: Optional[str] = None,
        publish_end: Optional[str] = None,
        keyword: Optional[str] = None,
        is_digest: Optional[int] = None,
        has_ai_result: Optional[int] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """List posts with filtering."""
        conditions = []
        params = []

        if publish_start:
            conditions.append("publish_time >= ?")
            params.append(publish_start)

        if publish_end:
            conditions.append("publish_time <= ?")
            params.append(publish_end)

        if keyword:
            conditions.append("title LIKE ?")
            params.append(f"%{keyword}%")

        if is_digest is not None:
            conditions.append("is_digest = ?")
            params.append(is_digest)

        if has_ai_result is not None:
            conditions.append("has_ai_result = ?")
            params.append(has_ai_result)

        if status:
            conditions.append("status = ?")
            params.append(status)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # Get total count
        count_sql = f"SELECT COUNT(*) as total FROM bbs_list WHERE {where_clause}"
        total_result = await db.fetchone(count_sql, tuple(params))
        total = total_result["total"] if total_result else 0

        # Get list
        offset = (page - 1) * page_size
        sql = f"""SELECT * FROM bbs_list
            WHERE {where_clause}
            ORDER BY publish_time DESC
            LIMIT ? OFFSET ?"""
        params.extend([page_size, offset])

        rows = await db.fetchall(sql, tuple(params))

        return {
            "items": rows,
            "total": total,
            "page": page,
            "page_size": page_size
        }

    @staticmethod
    async def get_post_detail(post_id: str) -> Optional[dict]:
        """Get post detail by post_id."""
        row = await db.fetchone(
            "SELECT * FROM bbs_list WHERE post_id = ?",
            (post_id,)
        )
        if row:
            data = dict(row)
            # Resolve md_file_path to actual content if available
            if data.get("md_file_path"):
                data["md_content"] = resolve_content(data["md_file_path"])
            if data.get("ai_result_path"):
                data["ai_result_content"] = resolve_content(data["ai_result_path"])
            return data
        return None

    @staticmethod
    async def trigger_analysis(
        post_id: str,
        md_file_path: Optional[str] = None,
        model: Optional[str] = None
    ) -> dict:
        """Trigger AI analysis for a post. Reads MD content, calls LLM, saves result."""
        # Fetch post info
        post = await db.fetchone(
            "SELECT * FROM bbs_list WHERE post_id = ?",
            (post_id,)
        )
        if not post:
            raise ValueError("帖子不存在")

        # Resolve content from md_file_path
        content = ""
        if md_file_path:
            content = resolve_content(md_file_path)
        elif post["md_file_path"]:
            content = resolve_content(post["md_file_path"])

        if not content:
            raise ValueError("帖子无内容，无法分析")

        # Truncate if too long (>8000 chars: head 3000 + tail 3000)
        if len(content) > 8000:
            content = content[:3000] + f"\n\n...[中间省略 {len(content) - 6000} 字]...\n\n" + content[-3000:]

        # Call LLM
        title = post["title"] or "未知标题"
        author = post["author_name"] or "未知作者"
        prompt = get_prompt(BBS_ANALYSIS_PROMPT, title=title, author=author, content=content)
        messages = [LLMMessage(role="user", content=prompt)]

        llm = llm_adapter.get_llm(model=model)
        response = await llm.chat(messages, temperature=0.3)

        # Save AI result to MD file
        rand_suffix = f"{random.randint(1000, 9999)}"
        ai_filename = f"AI-{post_id}-{rand_suffix}"
        ai_path = save_md("bbs_ai", ai_filename, response.content)

        # Update database
        await db.execute(
            """UPDATE bbs_list SET
                has_ai_result = 1,
                ai_result_path = ?
            WHERE post_id = ?""",
            (ai_path, post_id)
        )

        # Strategy linkage: extract strategy entity from post content
        strategy = None
        try:
            strategy = await StrategyService.extract_from_content(
                thread_id=post_id,
                title=title,
                content=content
            )
        except Exception as e:
            logger.info(f"Strategy extraction skipped for {post_id}: {e}")

        return {
            "post_id": post_id,
            "ai_result_path": ai_path,
            "model_used": response.model,
            "strategy": strategy,
            "message": "AI分析完成"
        }

    @staticmethod
    async def reanalyze_post(post_id: str) -> dict:
        """Re-trigger AI analysis for a post."""
        return await BBSService.trigger_analysis(
            post_id=post_id,
            md_file_path=None  # Will auto-resolve from DB
        )

    @staticmethod
    async def batch_analyze() -> dict:
        """Trigger AI analysis for all posts that are success but have no AI result."""
        rows = await db.fetchall(
            "SELECT post_id, md_file_path FROM bbs_list WHERE status = 'success' AND has_ai_result = 0",
            ()
        )

        results = []
        errors = []
        for row in rows:
            try:
                result = await BBSService.trigger_analysis(
                    post_id=row["post_id"],
                    md_file_path=row["md_file_path"]
                )
                results.append(result)
            except Exception as e:
                logger.warning(f"BBS batch analyze failed for {row['post_id']}: {e}")
                errors.append({"post_id": row["post_id"], "error": str(e)})

        return {
            "total": len(rows),
            "success": len(results),
            "failed": len(errors),
            "errors": errors
        }