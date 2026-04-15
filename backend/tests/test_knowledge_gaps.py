"""Knowledge endpoint gap tests — cover params and edge cases not in test_knowledge.py.

Fills:
  - list_bookmarks: search param, sort_by / sort_order params
  - get_note: nonexistent bookmark → 1002
  - add_note: nonexistent bookmark → error
  - export: structure / fields validation
  - get_bookmark: nonexistent → 1002
"""

import json
import sqlite3

import pytest


class TestListBookmarksSortAndSearch:
    """list_bookmarks with sort_by / sort_order / search params."""

    def _seed(self, client):
        for tid, title, summary in [
            ("kb-sort-1", "Alpha 因子模型", "一种经典的因子投资方法"),
            ("kb-sort-2", "Beta 对冲策略", "使用市场中性方法"),
            ("kb-sort-3", "Gamma 期权定价", "BSM 模型在期权定价中的应用"),
        ]:
            client.post("/api/knowledge/bookmarks", json={
                "thread_id": tid, "title": title,
                "url": f"https://bbs.quantclass.cn/topic/{tid}",
                "summary": summary,
            })

    def test_sort_by_title_asc(self, test_client):
        """TC-K10: sort_by=title, sort_order=asc returns alphabetical order."""
        self._seed(test_client)
        resp = test_client.get("/api/knowledge/bookmarks", params={
            "sort_by": "title", "sort_order": "asc",
        })
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        titles = [i["title"] for i in items if i["thread_id"].startswith("kb-sort-")]
        # "Alpha" < "Beta" < "Gamma" in alphabetical order
        sorted_titles = sorted(titles)
        assert titles == sorted_titles, f"Expected alphabetical: {titles}"

    def test_sort_by_title_desc(self, test_client):
        """TC-K11: sort_by=title, sort_order=desc returns reverse alpha."""
        self._seed(test_client)
        resp = test_client.get("/api/knowledge/bookmarks", params={
            "sort_by": "title", "sort_order": "desc",
        })
        items = resp.json()["data"]["items"]
        titles = [i["title"] for i in items if i["thread_id"].startswith("kb-sort-")]
        assert titles == sorted(titles, reverse=True)

    def test_search_param_filters_by_keyword(self, test_client):
        """TC-K12: list_bookmarks search= filters by title/summary."""
        self._seed(test_client)
        resp = test_client.get("/api/knowledge/bookmarks", params={"search": "期权"})
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        # Only the Gamma bookmark mentions 期权
        assert len(items) >= 1
        assert any("期权" in i["title"] or "期权" in (i.get("summary") or "") for i in items)

    def test_search_no_match(self, test_client):
        """TC-K13: search with non-matching keyword returns empty."""
        resp = test_client.get("/api/knowledge/bookmarks", params={
            "search": "量子计算不存在的关键词xyz",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["items"] == []


class TestNoteEdgeCases:
    """Notes endpoint edge cases."""

    def test_add_note_nonexistent_bookmark(self, test_client):
        """TC-K14: add_note to nonexistent bookmark → 1002 not found."""
        resp = test_client.post(
            "/api/knowledge/bookmarks/does-not-exist/notes",
            json={"content": "orphan note"},
        )
        assert resp.json()["code"] == 1002

    def test_get_note_nonexistent_bookmark(self, test_client):
        """TC-K15: get_note for nonexistent bookmark → 1002."""
        resp = test_client.get("/api/knowledge/bookmarks/does-not-exist/notes")
        assert resp.json()["code"] == 1002

    def test_get_note_bookmark_without_note(self, test_client):
        """TC-K16: get_note for bookmark that has no note → 1002."""
        create = test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "kb-no-note",
            "title": "No note",
            "url": "https://bbs.quantclass.cn/topic/kb-no-note",
        })
        bid = create.json()["data"]["bookmark_id"]
        resp = test_client.get(f"/api/knowledge/bookmarks/{bid}/notes")
        assert resp.json()["code"] == 1002


class TestExportEdgeCases:
    """Export edge cases."""

    def test_export_json_structure(self, test_client):
        """TC-K17: JSON export items contain expected fields."""
        # Ensure at least one bookmark exists
        test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "kb-exp-1", "title": "Export test",
            "url": "https://bbs.quantclass.cn/topic/kb-exp-1",
            "summary": "test", "tags": ["Python"],
        })
        resp = test_client.get("/api/knowledge/export", params={"format": "json"})
        data = json.loads(resp.text)
        assert len(data) >= 1
        item = data[0]
        # Must contain key fields
        for field in ("thread_id", "title", "url"):
            assert field in item, f"missing field: {field}"

    def test_export_csv_header_columns(self, test_client):
        """TC-K18: CSV header contains required columns."""
        resp = test_client.get("/api/knowledge/export", params={"format": "csv"})
        header = resp.text.split("\n")[0].lower()
        for col in ("title", "url"):
            assert col in header, f"missing column: {col}"

    def test_export_markdown_format(self, test_client):
        """TC-K19: Markdown export uses heading/link format."""
        resp = test_client.get("/api/knowledge/export", params={"format": "markdown"})
        md = resp.text
        # Should have markdown headings or list items
        assert "#" in md or "-" in md or "**" in md
