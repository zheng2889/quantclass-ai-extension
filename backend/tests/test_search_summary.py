"""Tests for search endpoints (TC-SR01 ~ TC-SR05)."""

import pytest


class TestSearch:
    """Search endpoint tests."""

    def _seed_bookmarks(self, test_client):
        """Seed some bookmarks for search tests."""
        bookmarks = [
            {"thread_id": "s1", "title": "趋势策略分析", "url": "https://bbs.quantclass.cn/topic/s1",
             "summary": "本文讨论了A股趋势追踪策略", "tags": ["量化策略"]},
            {"thread_id": "s2", "title": "均值回归研究", "url": "https://bbs.quantclass.cn/topic/s2",
             "summary": "均值回归在期货市场的应用", "tags": ["回测"]},
            {"thread_id": "s3", "title": "Python量化工具", "url": "https://bbs.quantclass.cn/topic/s3",
             "summary": "使用Python进行量化交易开发", "tags": ["Python"]},
        ]
        for b in bookmarks:
            test_client.post("/api/knowledge/bookmarks", json=b)

    def test_search_basic(self, test_client):
        """TC-SR01: Basic search returns relevant results."""
        self._seed_bookmarks(test_client)
        resp = test_client.post("/api/search", json={
            "query": "趋势策略"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "results" in body["data"]
        assert "pagination" in body["data"]

    def test_search_get(self, test_client):
        """Search via GET method."""
        resp = test_client.get("/api/search", params={"q": "Python"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0

    def test_search_no_results(self, test_client):
        """TC-SR04: Query with no matches returns empty results."""
        resp = test_client.post("/api/search", json={
            "query": "完全不相关的随机字符串xyz123"
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["results"] == [] or body["data"]["pagination"]["total"] == 0

    def test_search_empty_query(self, test_client):
        """TC-SR03: Empty query returns validation error."""
        resp = test_client.post("/api/search", json={
            "query": ""
        })
        # Pydantic validation returns 422
        assert resp.status_code == 422

    def test_search_chinese_fts5_hit(self, test_client):
        """FTS5 trigram tokenizer must find Chinese queries >= 3 chars.

        Regression: the original schema used the default `simple` tokenizer,
        which doesn't tokenize CJK at all — every Chinese query fell through
        to the LIKE fallback (score == 0). Switching to the trigram tokenizer
        means a 3+ char Chinese query should hit FTS5 and return a non-zero
        rank score.
        """
        self._seed_bookmarks(test_client)
        resp = test_client.post("/api/search", json={"query": "趋势策略"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        results = body["data"]["results"]
        assert len(results) >= 1
        # The seeded row "趋势策略分析" must be in the result set.
        titles = [r["title"] for r in results]
        assert any("趋势策略" in t for t in titles), f"trigram miss: {titles}"
        # And it must have come from FTS5 (score < 0, rank is negative),
        # not the LIKE fallback (score == 0).
        hit = next(r for r in results if "趋势策略" in r["title"])
        assert hit["score"] != 0, (
            "Expected FTS5 rank, got LIKE fallback — trigram tokenizer not active"
        )

    def test_search_score_is_normalized(self, test_client):
        """Search scores must be floats in [0, 1] so the frontend can render
        a sensible progress bar. Regression: the raw FTS5 ``rank`` column is
        a tiny negative BM25 value (~-1e-6) and was surfaced as-is, which
        the popup then multiplied by 100 to show `-0.0%` to every user."""
        self._seed_bookmarks(test_client)
        resp = test_client.post("/api/search", json={"query": "趋势策略"})
        body = resp.json()
        results = body["data"]["results"]
        assert len(results) >= 1
        for r in results:
            s = r["score"]
            assert isinstance(s, (int, float)), f"score must be numeric, got {type(s)}"
            assert 0.0 <= s <= 1.0, f"score {s} out of [0,1]"
        # Best hit must max out at 1.0 (it sits at the top of the normalized range).
        assert max(r["score"] for r in results) == 1.0

    def test_search_score_like_fallback_flat(self, test_client):
        """LIKE-fallback hits (no real ranking) should get a mid-tier 0.5 so
        the UI bar is still visible without overstating confidence."""
        self._seed_bookmarks(test_client)
        resp = test_client.post("/api/search", json={"query": "期货"})
        body = resp.json()
        results = body["data"]["results"]
        assert len(results) >= 1
        for r in results:
            assert r["score"] == 0.5

    def test_search_normalization_with_multiple_fts_hits(self, test_client):
        """With 2+ distinct FTS5 hits the normalizer must do the linear
        rescale (``(raw - worst) / (best - worst)``). Our existing
        chinese_fts5_hit test only had a single match per query, so the
        branch collapsed to the ``denom == 0 → score = 1.0`` short-circuit
        and lines 57-58 of ``_normalize_scores`` never ran.

        Both seeded titles share the trigrams {趋势策, 势策略} so querying
        "趋势策略" (which decomposes to exactly those trigrams) will match
        both rows with different BM25 ranks — one title is longer which
        gives it a worse rank, so the rescale should map one row to 1.0
        and the other strictly below 1.0.
        """
        for i, title in enumerate(["mfh 趋势策略", "mfh 趋势策略 的长标题含更多字"]):
            test_client.post("/api/knowledge/bookmarks", json={
                "thread_id": f"mfh-{i}",
                "title": title,
                "url": f"https://bbs.quantclass.cn/topic/mfh-{i}",
                "summary": "payload",
            })
        resp = test_client.post("/api/search", json={"query": "趋势策略"})
        body = resp.json()
        results = body["data"]["results"]
        # Must have ≥ 2 hits from the multi-hit rescale path. We also
        # filter to the mfh- prefix so prior test seeds don't leak in
        # and confuse the scoring assertion.
        mfh_hits = [r for r in results if r["thread_id"].startswith("mfh-")]
        assert len(mfh_hits) >= 2
        # Scores must span the normalized range: best hit = 1.0, worst < 1.
        scores = sorted((r["score"] for r in mfh_hits), reverse=True)
        assert scores[0] == 1.0
        assert scores[-1] < 1.0  # proves the (raw - worst) / denom branch ran

    def test_search_suggestions_include_multi_word_prefix(self, test_client):
        """``_generate_suggestions`` prepends the first two words when
        the query has 2+ tokens. Covers line 195."""
        resp = test_client.post("/api/search", json={
            "query": "quant trading python",
        })
        body = resp.json()
        suggestions = body["data"]["suggestions"]
        # The compound prefix "quant trading" should appear somewhere
        # in the suggestions list, ahead of single-word alternatives.
        assert any("quant trading" in s for s in suggestions)

    def test_search_chinese_short_query_like_fallback(self, test_client):
        """2-char CJK queries are below trigram's minimum length — they must
        still resolve via the LIKE fallback rather than returning empty."""
        self._seed_bookmarks(test_client)
        # "期货" appears only in the summary of the 均值回归 bookmark.
        resp = test_client.post("/api/search", json={"query": "期货"})
        assert resp.status_code == 200
        body = resp.json()
        results = body["data"]["results"]
        assert len(results) >= 1
        titles = [r["title"] for r in results]
        assert any("均值回归" in t for t in titles), f"LIKE fallback miss: {titles}"


class TestSummary:
    """Summary endpoint tests (non-LLM)."""

    def test_get_nonexistent_summary(self, test_client):
        """TC-S09: Get summary for non-existent thread returns 1002."""
        resp = test_client.get("/api/summary/nonexistent999")
        assert resp.json()["code"] == 1002

    def test_list_summaries_empty(self, test_client):
        """List summaries returns paginated result."""
        resp = test_client.get("/api/summary/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert "items" in body["data"]
        assert "pagination" in body["data"]

    def test_generate_summary_empty_content(self, test_client):
        """TC-S04: Empty content returns validation error."""
        resp = test_client.post("/api/summary/generate", json={
            "thread_id": "test",
            "title": "Test",
            "content": ""
        })
        # Pydantic validation: min_length=1
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_summary_filters_expired(self, test_client):
        """TC-S10: A summary past its expires_at is treated as a cache miss.

        Regression: the schema stored expires_at on INSERT but get_summary
        never filtered on it, so a 40-day-old summary would still be served
        as fresh, violating the 30-day TTL in PRD §2.1.
        """
        from database.connection import db
        from services.summary_service import SummaryService

        # Seed a row that expired yesterday (+08:00 timezone to match DB).
        await db.execute(
            """INSERT INTO summaries
               (thread_id, title, content_hash, summary, auto_tags,
                model_used, tokens_used, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "expired-thread",
                "Stale post",
                "deadbeef" * 4,
                "old summary text",
                "[]",
                "test-model",
                0,
                "2020-01-01T00:00:00+08:00",
            ),
        )

        # Default path treats it as a miss.
        assert await SummaryService.get_summary("expired-thread") is None
        # include_expired bypasses the filter so cleanup code can still see it.
        raw = await SummaryService.get_summary("expired-thread", include_expired=True)
        assert raw is not None
        assert raw["summary"] == "old summary text"

        # And the API endpoint surfaces the filtered result as 1002 (not found)
        # so the client knows to regenerate.
        resp = test_client.get("/api/summary/expired-thread")
        assert resp.json()["code"] == 1002

    @pytest.mark.asyncio
    async def test_cleanup_expired_summaries_removes_stale_rows(self, test_client):
        """cleanup_expired_summaries should delete past-TTL rows and leave
        fresh ones alone, returning an accurate rowcount."""
        from database.connection import db
        from services.summary_service import SummaryService

        await db.execute("DELETE FROM summaries")

        # Two expired, one fresh.
        await db.execute(
            """INSERT INTO summaries
               (thread_id, title, content_hash, summary, auto_tags,
                model_used, tokens_used, expires_at)
               VALUES
               ('stale-1', 't', 'h1', 's', '[]', 'm', 0, '2020-01-01T00:00:00+08:00'),
               ('stale-2', 't', 'h2', 's', '[]', 'm', 0, '2021-06-15T12:00:00+08:00'),
               ('fresh-1', 't', 'h3', 's', '[]', 'm', 0, '2099-12-31T00:00:00+08:00')"""
        )

        removed = await SummaryService.cleanup_expired_summaries()
        assert removed == 2

        remaining = await db.fetchall("SELECT thread_id FROM summaries")
        ids = {row["thread_id"] for row in remaining}
        assert ids == {"fresh-1"}

        # Idempotent: a second sweep removes nothing.
        assert await SummaryService.cleanup_expired_summaries() == 0

    def test_truncate_long_content_preserves_head_and_tail(self):
        """Pure unit: ``_truncate_content`` must pass through content ≤8000
        chars unchanged, and for longer content keep the first 3000 and
        last 3000 chars with an explicit omission marker in between. The
        3000/3000 window is spec'd in the docstring and matches PRD
        §2.1's truncation rule."""
        from services.summary_service import SummaryService

        short = "x" * 8000
        assert SummaryService._truncate_content(short) == short

        long = "A" * 3000 + "B" * 6000 + "C" * 3000  # 12000 chars
        result = SummaryService._truncate_content(long)
        assert result.startswith("A" * 3000)
        assert result.endswith("C" * 3000)
        assert "中间省略 6000 字" in result
        # The middle must have been dropped.
        assert "B" * 6000 not in result

    @pytest.mark.asyncio
    async def test_same_content_expired_refreshes_ttl_without_llm(self):
        """Cache-hit with matching content_hash but an elapsed TTL should
        bump expires_at in place and NOT call the LLM again. Regression:
        the earlier implementation treated expired rows as a cache miss
        and burned tokens regenerating identical content."""
        from database.connection import db
        from services.summary_service import SummaryService
        from tests.fake_llm import fake_llm_singleton

        # Compute the hash we're going to seed the row with so the
        # generate_summary call sees a match and takes the refresh path.
        content = "量化策略的回测方法与实盘表现的对比分析"
        content_hash = SummaryService._compute_hash(content)

        await db.execute("DELETE FROM summaries WHERE thread_id = ?", ("refresh-1",))
        await db.execute(
            """INSERT INTO summaries
               (thread_id, title, content_hash, summary, auto_tags,
                model_used, tokens_used, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "refresh-1",
                "旧标题",
                content_hash,
                "cached body",
                "[]",
                "old-model",
                0,
                "2020-01-01T00:00:00+08:00",  # expired
            ),
        )

        calls_before = fake_llm_singleton.calls
        result = await SummaryService.generate_summary(
            thread_id="refresh-1",
            title="旧标题",
            content=content,
        )
        assert fake_llm_singleton.calls == calls_before  # NO LLM call
        assert result["summary"] == "cached body"
        # TTL moved into the future.
        row = await db.fetchone(
            "SELECT expires_at FROM summaries WHERE thread_id = ?",
            ("refresh-1",),
        )
        assert row["expires_at"] > SummaryService._now_iso()

    @pytest.mark.asyncio
    async def test_delete_summary_removes_row_and_reports_bool(self):
        """``delete_summary`` returns True when it removed a row and
        False when nothing matched. This is the path the DELETE route
        uses to decide between 200 and 404."""
        from database.connection import db
        from services.summary_service import SummaryService

        await db.execute(
            """INSERT INTO summaries
               (thread_id, title, content_hash, summary, auto_tags,
                model_used, tokens_used, expires_at)
               VALUES ('del-1', 't', 'h', 's', '[]', 'm', 0, '2099-12-31T00:00:00+08:00')"""
        )

        ok = await SummaryService.delete_summary("del-1")
        assert ok is True
        gone = await SummaryService.delete_summary("del-1")
        assert gone is False  # second delete is a no-op
        missing = await SummaryService.delete_summary("never-existed")
        assert missing is False

    @pytest.mark.asyncio
    async def test_generate_tags_returns_empty_on_llm_failure(self, monkeypatch):
        """``_generate_tags`` is wrapped in a broad except that swallows
        any LLM failure and returns an empty list — the contract is
        "never block a summary just because the tag call blew up".
        Regression-proof this so a future refactor doesn't leak the
        exception up to the caller."""
        from llm import adapter
        from services.summary_service import SummaryService

        class _BoomLLM:
            model = "boom"
            async def chat(self, *args, **kwargs):
                raise RuntimeError("simulated LLM tag failure")

        monkeypatch.setattr(adapter.llm_adapter, "get_llm", lambda **_: _BoomLLM())

        tags = await SummaryService._generate_tags("content", "summary")
        assert tags == []

    @pytest.mark.asyncio
    async def test_stream_generate_updates_existing_row(self, test_client):
        """SSE stream path with an already-existing row (same thread_id,
        different content) must take the UPDATE branch. Covers
        summary_service.py:220-230."""
        from database.connection import db

        # Pre-seed a row that will be updated.
        await db.execute(
            """INSERT INTO summaries
               (thread_id, title, content_hash, summary, auto_tags,
                model_used, tokens_used, expires_at)
               VALUES ('stream-upd', 'old title', 'OLD-HASH',
                       'old body', '[]', 'old-model', 0,
                       '2099-12-31T00:00:00+08:00')"""
        )

        with test_client.stream(
            "POST", "/api/summary/generate",
            json={
                "thread_id": "stream-upd",
                "title": "new title",
                "content": "全新的内容，会让 content_hash 变化",
                "stream": True,
            },
        ) as resp:
            assert resp.status_code == 200
            # Drain the SSE body so the generator's finally block runs.
            body = b"".join(resp.iter_bytes())
        assert b"data:" in body

        row = await db.fetchone(
            "SELECT title, content_hash, summary FROM summaries WHERE thread_id = ?",
            ("stream-upd",),
        )
        assert row["title"] == "new title"
        assert row["content_hash"] != "OLD-HASH"
        assert row["summary"] != "old body"

    @pytest.mark.asyncio
    async def test_stream_generate_emits_error_event_on_llm_failure(
        self, test_client, monkeypatch
    ):
        """If ``chat_stream`` raises mid-flight, the SSE endpoint must
        surface an ``{"type": "error", "message": ...}`` event instead
        of letting the exception escape. Covers summary_service.py:243-245."""
        from tests.fake_llm import fake_llm_singleton

        async def _boom_stream(*args, **kwargs):
            # Must look like an async iterator — raise on first iteration.
            raise RuntimeError("simulated stream failure")
            yield  # pragma: no cover  (marks this as a generator)

        monkeypatch.setattr(fake_llm_singleton, "chat_stream", _boom_stream)

        with test_client.stream(
            "POST", "/api/summary/generate",
            json={
                "thread_id": "stream-err",
                "title": "err title",
                "content": "some content",
                "stream": True,
            },
        ) as resp:
            assert resp.status_code == 200
            body = b"".join(resp.iter_bytes()).decode("utf-8")
        assert '"type": "error"' in body
        assert "simulated stream failure" in body
