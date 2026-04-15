"""Knowledge-base end-to-end workflow test.

Runs the full lifecycle purely through HTTP (no browser, no extension):

  收藏 → 打标签 → AI 标签建议 → 写笔记 → 搜索命中 → 导出三格式验证 → 删除清理

This proves the knowledge feature works as a standalone backend — the
extension is just a UI shell on top.
"""

import json
import csv
import io

import pytest


class TestKnowledgeWorkflow:
    """Single flow covering the complete knowledge-base lifecycle."""

    # ---- helpers ----

    @staticmethod
    def _create_bookmark(client, thread_id, title, summary="", tags=None):
        resp = client.post("/api/knowledge/bookmarks", json={
            "thread_id": thread_id,
            "title": title,
            "url": f"https://bbs.quantclass.cn/topic/{thread_id}",
            "summary": summary,
            "tags": tags or [],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0, body
        return body["data"]["bookmark_id"]

    # ---- the workflow ----

    def test_full_lifecycle(self, test_client):
        """
        Step 1: 收藏两篇帖子（带标签）
        Step 2: AI 建议标签
        Step 3: 更新收藏追加标签
        Step 4: 添加笔记
        Step 5: 搜索命中
        Step 6: 导出 JSON / CSV / Markdown 验证
        Step 7: 删除其中一篇
        Step 8: 再次搜索 + 导出，验证数据一致
        """
        # ── Step 1: 收藏 ──
        bid1 = self._create_bookmark(
            test_client, "wf-1001",
            "双均线交叉策略回测",
            summary="使用 5 日均线与 20 日均线金叉做多、死叉做空的经典策略",
            tags=["量化策略"],
        )
        bid2 = self._create_bookmark(
            test_client, "wf-1002",
            "机器学习因子挖掘",
            summary="用 XGBoost 从 200 个候选因子中筛选出有效因子",
            tags=["机器学习"],
        )

        # ── Step 2: AI 标签建议 ──
        resp = test_client.post("/api/tags/suggest", json={
            "content": "双均线交叉策略回测，使用 5 日均线与 20 日均线",
            "existing_tags": ["量化策略"],
            "max_suggestions": 3,
        })
        assert resp.status_code == 200
        suggestions = resp.json()["data"]["suggested_tags"]
        assert len(suggestions) >= 1
        # FakeLLM returns "量化策略, 回测, 趋势跟踪"; "量化策略" is filtered.
        new_tag_names = [s["name"] for s in suggestions]
        assert "量化策略" not in new_tag_names  # existing excluded

        # ── Step 3: 把 AI 建议的标签追加到第一条收藏 ──
        resp = test_client.put(f"/api/knowledge/bookmarks/{bid1}", json={
            "tags": ["量化策略"] + new_tag_names[:2],
        })
        assert resp.json()["code"] == 0
        updated_tags = resp.json()["data"]["tags"]
        assert len(updated_tags) >= 2

        # ── Step 4: 给两条收藏各写一条笔记 ──
        resp = test_client.post(f"/api/knowledge/bookmarks/{bid1}/notes", json={
            "content": "回测夏普比率 1.3，最大回撤 15%，适合趋势市。",
        })
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["content"].startswith("回测夏普")

        resp = test_client.post(f"/api/knowledge/bookmarks/{bid2}/notes", json={
            "content": "筛选出 12 个有效因子，但需要注意过拟合风险。",
        })
        assert resp.json()["code"] == 0

        # ── Step 5: 搜索 ──
        # 5a: 搜索第一篇的关键词
        resp = test_client.post("/api/search", json={"query": "均线交叉"})
        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        titles = [r["title"] for r in results]
        assert any("双均线" in t for t in titles), f"expected hit: {titles}"

        # 5b: 按标签过滤
        resp = test_client.get("/api/knowledge/bookmarks", params={"tag": "机器学习"})
        items = resp.json()["data"]["items"]
        assert len(items) >= 1
        assert all("机器学习" in i["tags"] for i in items)

        # ── Step 6: 导出三种格式 ──
        # 6a: JSON
        resp = test_client.get("/api/knowledge/export", params={"format": "json"})
        assert resp.status_code == 200
        assert "application/json" in resp.headers["content-type"]
        exported = json.loads(resp.text)
        assert isinstance(exported, list)
        exported_ids = {b["thread_id"] for b in exported}
        assert "wf-1001" in exported_ids
        assert "wf-1002" in exported_ids

        # 6b: CSV
        resp = test_client.get("/api/knowledge/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        header = rows[0]
        assert "Title" in header or "title" in [h.lower() for h in header]
        # Data rows present
        assert len(rows) >= 3  # header + at least 2 bookmarks

        # 6c: Markdown
        resp = test_client.get("/api/knowledge/export", params={"format": "markdown"})
        assert resp.status_code == 200
        assert "text/markdown" in resp.headers["content-type"]
        md = resp.text
        assert "双均线交叉策略回测" in md
        assert "机器学习因子挖掘" in md

        # ── Step 7: 删除第一条 ──
        resp = test_client.delete(f"/api/knowledge/bookmarks/{bid1}")
        assert resp.json()["data"]["deleted"] is True

        # 确认已删除
        resp = test_client.get(f"/api/knowledge/bookmarks/{bid1}")
        assert resp.json()["code"] == 1002

        # ── Step 8: 删除后的一致性 ──
        # 8a: 搜索不再命中已删除条目
        resp = test_client.post("/api/search", json={"query": "均线交叉"})
        results = resp.json()["data"]["results"]
        remaining_titles = [r["title"] for r in results]
        assert not any("双均线" in t for t in remaining_titles), \
            f"deleted bookmark still searchable: {remaining_titles}"

        # 8b: 导出不再包含已删除条目
        resp = test_client.get("/api/knowledge/export", params={"format": "json"})
        exported = json.loads(resp.text)
        exported_ids = {b["thread_id"] for b in exported}
        assert "wf-1001" not in exported_ids
        assert "wf-1002" in exported_ids  # 第二条仍在

        # 8c: 第二条笔记仍可读
        resp = test_client.get(f"/api/knowledge/bookmarks/{bid2}/notes")
        assert resp.json()["code"] == 0
        assert "过拟合" in resp.json()["data"]["content"]

        # ── cleanup: delete the second one too ──
        test_client.delete(f"/api/knowledge/bookmarks/{bid2}")
