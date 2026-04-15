"""Coverage for the advanced_search service + /api/search/advanced endpoint.

Before this file, ``services/search_service.py::advanced_search`` (lines
210-283) and ``routers/search.py::/advanced`` (lines 58-70) were completely
uncovered — the method existed, was routed, and shipped in the docs, but
nothing exercised it end-to-end. These tests hit the router so both layers
get credit in coverage.

Tests pin the behavior of each filter (title, content, tags, date range)
and the combinators between them. Each test seeds its own rows with a
unique ``adv-`` prefix so parallel bookmarks from other test modules
(``test_knowledge``, ``test_search_summary``) don't bleed in.
"""

import pytest

# Distinct namespace so we don't collide with bookmarks seeded by other
# test files — the test_client fixture is session-scoped, so the DB
# accumulates rows across modules.
PFX = "adv"


def _bm(thread_id_suffix, title, summary, tags=None, url=None):
    return {
        "thread_id": f"{PFX}-{thread_id_suffix}",
        "title": title,
        "url": url or f"https://bbs.quantclass.cn/topic/{PFX}-{thread_id_suffix}",
        "summary": summary,
        "tags": tags or [],
    }


def _seed(test_client, rows):
    created = []
    for row in rows:
        resp = test_client.post("/api/knowledge/bookmarks", json=row)
        assert resp.status_code == 200
        created.append(resp.json()["data"])
    return created


def _advanced(test_client, **params):
    """POST /api/search/advanced with query-string parameters.

    FastAPI's advanced_search handler declares filter arguments as plain
    Python keyword args, which default to query-string binding — not a
    request body — so we pass them via ``params`` even though it's a POST.
    """
    resp = test_client.post("/api/search/advanced", params=params)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    return body["data"]


def _titles(data):
    return [r["title"] for r in data["results"]]


class TestAdvancedSearch:
    """Cover the multi-filter advanced_search path end-to-end."""

    def test_no_filters_returns_paginated_results(self, test_client):
        """Empty filter set still hits the happy path (no WHERE clause)
        and returns a well-formed pagination envelope."""
        _seed(test_client, [
            _bm("nf1", "无过滤器测试 A", "summary A"),
            _bm("nf2", "无过滤器测试 B", "summary B"),
        ])
        data = _advanced(test_client)
        assert "results" in data
        assert "pagination" in data
        pg = data["pagination"]
        assert pg["page"] == 1
        assert pg["page_size"] == 20
        assert pg["total"] >= 2
        assert pg["total_pages"] >= 1
        # Query echo — lets the client render "你搜的是什么" without
        # rebuilding the payload itself.
        assert "query" in data
        assert data["query"]["title"] is None
        assert data["query"]["tags"] is None

    def test_title_filter_matches_like_substring(self, test_client):
        """``title`` filter maps to ``b.title LIKE '%…%'``."""
        _seed(test_client, [
            _bm("t1", "量化因子分析深入", "因子相关内容"),
            _bm("t2", "不相关的随笔", "杂谈"),
        ])
        data = _advanced(test_client, title="因子分析")
        titles = _titles(data)
        assert any("因子分析" in t for t in titles)
        assert "不相关的随笔" not in titles

    def test_content_filter_searches_title_and_summary(self, test_client):
        """``content`` filter fans out to (summary LIKE ? OR title LIKE ?),
        so a keyword only in the summary should still surface the row."""
        _seed(test_client, [
            _bm("c1", "策略回测框架", "本文讨论了止盈止损的实现细节"),
            _bm("c2", "其他文章", "讲的是日历效应"),
        ])
        data = _advanced(test_client, content="止盈止损")
        titles = _titles(data)
        assert "策略回测框架" in titles
        assert "其他文章" not in titles

    def test_tags_filter_uses_exists_subquery(self, test_client):
        """``tags`` filter hits the EXISTS subquery joining
        bookmark_tags + tags. Multi-tag should be OR (IN), not AND."""
        _seed(test_client, [
            _bm("tg1", "带标签文章 A", "a", tags=["adv-tag-alpha"]),
            _bm("tg2", "带标签文章 B", "b", tags=["adv-tag-beta"]),
            _bm("tg3", "带标签文章 C", "c", tags=["adv-tag-gamma"]),
        ])
        # Single tag
        data = _advanced(test_client, tags=["adv-tag-alpha"])
        titles = _titles(data)
        assert "带标签文章 A" in titles
        assert "带标签文章 B" not in titles

        # Multi-tag: OR semantics via IN (...)
        data = _advanced(test_client, tags=["adv-tag-alpha", "adv-tag-beta"])
        titles = _titles(data)
        assert "带标签文章 A" in titles
        assert "带标签文章 B" in titles
        assert "带标签文章 C" not in titles

    def test_date_range_filter(self, test_client):
        """``date_from``/``date_to`` bind to ``b.created_at``. We can't
        control created_at at insert time (the DB fills it in), so we
        instead seed a fresh bookmark and query with a date_from that
        falls *before* the insert — every fresh row should be returned.
        Then query with a date_from set far in the future to confirm the
        filter excludes everything."""
        _seed(test_client, [_bm("dr1", "日期范围测试", "payload")])

        # date_from past → should include the fresh row
        # Use large page_size because session-scoped DB may have >20 bookmarks.
        data = _advanced(test_client, date_from="2000-01-01T00:00:00+08:00", page_size=100)
        assert any("日期范围测试" in t for t in _titles(data))

        # date_from future → should exclude it
        data = _advanced(test_client, date_from="2099-12-31T23:59:59+08:00", page_size=100)
        assert all("日期范围测试" not in t for t in _titles(data))

        # date_to past → should exclude the fresh row (nothing created before 2000)
        data = _advanced(test_client, date_to="2000-12-31T00:00:00+08:00", page_size=100)
        assert all("日期范围测试" not in t for t in _titles(data))

        # Both date_from AND date_to wrapping the present → should include it
        data = _advanced(
            test_client,
            date_from="2000-01-01T00:00:00+08:00",
            date_to="2099-12-31T23:59:59+08:00",
            page_size=100,
        )
        assert any("日期范围测试" in t for t in _titles(data))

    def test_combined_filters_are_and(self, test_client):
        """Multiple filters should AND together: a row must match all of
        title + tags + content to surface."""
        _seed(test_client, [
            _bm("cm1", "组合过滤 策略 A", "止盈", tags=["adv-tag-cm"]),
            _bm("cm2", "组合过滤 策略 B", "其他", tags=["adv-tag-cm"]),
            _bm("cm3", "无关文章",         "止盈", tags=["adv-tag-cm"]),
        ])
        data = _advanced(
            test_client,
            title="组合过滤",
            content="止盈",
            tags=["adv-tag-cm"],
        )
        titles = _titles(data)
        assert "组合过滤 策略 A" in titles
        assert "组合过滤 策略 B" not in titles  # content mismatch
        assert "无关文章" not in titles           # title mismatch

    def test_pagination_respects_page_size(self, test_client):
        """page_size=1 with multiple matches → pagination reports
        total_pages >= 2 and each page returns at most 1 row."""
        _seed(test_client, [
            _bm("pg1", "分页测试条目", "payload 1"),
            _bm("pg2", "分页测试条目", "payload 2"),
            _bm("pg3", "分页测试条目", "payload 3"),
        ])
        data = _advanced(test_client, title="分页测试条目", page=1, page_size=1)
        assert len(data["results"]) == 1
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 1
        assert data["pagination"]["total"] >= 3
        assert data["pagination"]["total_pages"] >= 3

        # Second page should return a different row — or at least advance
        # the offset; we can't assert strict ordering without a stable
        # sort key, but we can prove the page number echoes back.
        data2 = _advanced(test_client, title="分页测试条目", page=2, page_size=1)
        assert data2["pagination"]["page"] == 2
        assert len(data2["results"]) == 1


class TestReindex:
    """Cover ``SearchService.reindex`` — both the happy path and the
    except-branch that silently swallows failures and returns
    ``{success: False}`` instead of raising."""

    @pytest.mark.asyncio
    async def test_reindex_happy_path(self, test_client):
        """Seed one bookmark, trigger rebuild, expect indexed_count >= 1."""
        from services.search_service import SearchService
        test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "reidx-1",
            "title": "reindex 幂等测试",
            "url": "https://bbs.quantclass.cn/topic/reidx-1",
            "summary": "payload",
        })
        result = await SearchService.reindex()
        assert result["success"] is True
        assert result["indexed_count"] >= 1
        assert "rebuilt" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_reindex_swallows_exception(self, monkeypatch, test_client):
        """If the FTS rebuild statement blows up (corrupted index, bad
        disk, etc.), reindex must return a structured failure envelope
        instead of propagating — admin clients rely on the
        ``{success: False, message, indexed_count: 0}`` shape."""
        from services.search_service import SearchService
        from database.connection import db

        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated FTS rebuild failure")

        monkeypatch.setattr(db, "execute", _boom)

        result = await SearchService.reindex()
        assert result["success"] is False
        assert result["indexed_count"] == 0
        assert "simulated FTS rebuild failure" in result["message"]
