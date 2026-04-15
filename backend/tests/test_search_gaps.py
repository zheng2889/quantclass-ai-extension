"""Search endpoint gap tests.

Fills:
  TC-SR05 top_k / page_size 限制
  TC-SR06 GET search with pagination
  TC-SR07 POST search with page > 1
  TC-SR08 search result fields structure
"""


class TestSearchPagination:
    """Pagination behaviour for both GET and POST search."""

    def _seed(self, client):
        for i in range(5):
            client.post("/api/knowledge/bookmarks", json={
                "thread_id": f"sr-pg-{i}",
                "title": f"搜索分页测试 item{i}",
                "url": f"https://bbs.quantclass.cn/topic/sr-pg-{i}",
                "summary": f"用于分页测试的内容 item{i}",
            })

    def test_post_search_page_size(self, test_client):
        """TC-SR05: page_size limits number of returned results."""
        self._seed(test_client)
        resp = test_client.post("/api/search", json={
            "query": "分页测试",
            "pagination": {"page": 1, "page_size": 2},
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["results"]) <= 2
        assert data["pagination"]["page_size"] == 2

    def test_post_search_page_2(self, test_client):
        """TC-SR07: page > 1 skips earlier results."""
        self._seed(test_client)
        r1 = test_client.post("/api/search", json={
            "query": "分页测试",
            "pagination": {"page": 1, "page_size": 2},
        })
        r2 = test_client.post("/api/search", json={
            "query": "分页测试",
            "pagination": {"page": 2, "page_size": 2},
        })
        ids1 = {r["thread_id"] for r in r1.json()["data"]["results"]}
        ids2 = {r["thread_id"] for r in r2.json()["data"]["results"]}
        # Pages should not overlap
        assert ids1.isdisjoint(ids2) or len(ids2) == 0

    def test_get_search_pagination(self, test_client):
        """TC-SR06: GET /api/search?q=...&page_size=2 also paginates."""
        self._seed(test_client)
        resp = test_client.get("/api/search", params={
            "q": "分页测试", "page": 1, "page_size": 2,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["results"]) <= 2


class TestSearchResultStructure:
    """TC-SR08: Each result item has expected fields."""

    def test_result_fields(self, test_client):
        test_client.post("/api/knowledge/bookmarks", json={
            "thread_id": "sr-fields-1",
            "title": "字段结构测试",
            "url": "https://bbs.quantclass.cn/topic/sr-fields-1",
            "summary": "用于验证结果字段",
        })
        resp = test_client.post("/api/search", json={"query": "字段结构"})
        results = resp.json()["data"]["results"]
        assert len(results) >= 1
        item = results[0]
        for field in ("thread_id", "title", "url", "score"):
            assert field in item, f"missing field: {field}"
