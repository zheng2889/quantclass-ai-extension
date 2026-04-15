"""Summary endpoint gap tests — cover TC-S cases not yet automated.

Fills:
  TC-S03 超长内容截断
  TC-S05 LLM 调用失败（API Key 无效模拟）
  TC-S07 流式输出（补充 language=English 分支）
  TC-S08 获取已缓存摘要 (happy path GET after generate)
  TC-S09 已有（in test_search_summary, repeated here for completeness ref）
  TC-S10 HTML 内容解析（content 含 HTML 标签）
  delete nonexistent summary → 1002
  list_summaries with data + pagination
"""

import json

import pytest

from tests.fake_llm import push_response, fake_llm_singleton


class TestSummaryHappyPath:
    """Happy-path sequences that go through the full generate → get → list → delete cycle."""

    def test_generate_then_get(self, test_client):
        """TC-S08: GET /api/summary/{id} returns cached summary after generate."""
        test_client.post("/api/summary/generate", json={
            "thread_id": "sg-get-1",
            "title": "缓存读取测试",
            "content": "正常内容用于测试 GET 缓存命中" * 5,
            "stream": False,
            "auto_tags": False,
        })
        resp = test_client.get("/api/summary/sg-get-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["thread_id"] == "sg-get-1"
        assert body["data"]["summary"]  # non-empty
        assert body["data"]["title"] == "缓存读取测试"

    def test_list_summaries_with_data(self, test_client):
        """TC-S11: list_summaries returns items + correct pagination after seeding."""
        # Generate a couple summaries
        for i in range(3):
            test_client.post("/api/summary/generate", json={
                "thread_id": f"sg-list-{i}",
                "title": f"List test {i}",
                "content": f"列表测试内容 {i}" * 5,
                "stream": False,
                "auto_tags": False,
            })
        resp = test_client.get("/api/summary/", params={"page": 1, "page_size": 2})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) <= 2
        assert data["pagination"]["total"] >= 3
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2

    def test_delete_existing_summary(self, test_client):
        """TC-S12: DELETE existing summary returns deleted=True then 404."""
        test_client.post("/api/summary/generate", json={
            "thread_id": "sg-del-1",
            "title": "To be deleted",
            "content": "删除测试" * 5,
            "stream": False,
            "auto_tags": False,
        })
        resp = test_client.delete("/api/summary/sg-del-1")
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["deleted"] is True
        # Now gone
        resp = test_client.get("/api/summary/sg-del-1")
        assert resp.json()["code"] == 1002

    def test_delete_nonexistent_summary(self, test_client):
        """TC-S13: DELETE non-existent summary → 1002."""
        resp = test_client.delete("/api/summary/does-not-exist-xyz")
        assert resp.json()["code"] == 1002


class TestSummaryLongContent:
    """TC-S03: 超长内容截断."""

    def test_long_content_accepted(self, test_client):
        """20000 字 content still generates successfully (truncated internally)."""
        long_content = "这是一段长文本。" * 3000  # ~21000 chars
        resp = test_client.post("/api/summary/generate", json={
            "thread_id": "sg-long-1",
            "title": "超长内容",
            "content": long_content,
            "stream": False,
            "auto_tags": False,
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["summary"]


class TestSummaryLanguage:
    """TC-S07 supplement: language=English branch."""

    def test_generate_with_english_language(self, test_client):
        """language='English' is passed to the prompt without error."""
        resp = test_client.post("/api/summary/generate", json={
            "thread_id": "sg-lang-en",
            "title": "English summary",
            "content": "Testing English language parameter" * 10,
            "stream": False,
            "auto_tags": False,
            "language": "English",
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    def test_stream_with_english_language(self, test_client):
        """SSE stream also accepts language='English'."""
        resp = test_client.post("/api/summary/generate", json={
            "thread_id": "sg-lang-en-sse",
            "title": "English SSE",
            "content": "Testing English stream" * 10,
            "stream": True,
            "auto_tags": False,
            "language": "English",
        })
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "done" in types


class TestSummaryHTMLContent:
    """TC-S10: content 包含 HTML 标签仍正常生成。"""

    def test_html_content_does_not_break(self, test_client):
        content = """
        <div class="post-body">
          <h2>策略分析</h2>
          <p>这是一段<strong>加粗</strong>的内容，包含<a href="#">链接</a>。</p>
          <pre><code>import pandas as pd</code></pre>
          <script>alert('xss')</script>
        </div>
        """ * 3
        resp = test_client.post("/api/summary/generate", json={
            "thread_id": "sg-html-1",
            "title": "HTML Content",
            "content": content,
            "stream": False,
            "auto_tags": False,
        })
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["summary"]


class TestSummaryLLMFailure:
    """TC-S05 / TC-S06: LLM failure scenarios."""

    def test_llm_error_nonstream_returns_llm_error(self, test_client):
        """TC-S05: When LLM raises, non-stream endpoint returns code=2001."""
        # Push an error-trigger: FakeLLM won't raise by default, so we
        # monkey-patch it for this single test.
        original_chat = fake_llm_singleton.chat

        async def _raise_chat(*args, **kwargs):
            raise RuntimeError("Simulated API key invalid")

        fake_llm_singleton.chat = _raise_chat
        try:
            resp = test_client.post("/api/summary/generate", json={
                "thread_id": "sg-err-1",
                "title": "Error test",
                "content": "内容" * 10,
                "stream": False,
                "auto_tags": False,
            })
            # Router catches Exception and returns llm_error (code=2001)
            body = resp.json()
            assert body["code"] == 2001, body
        finally:
            fake_llm_singleton.chat = original_chat

    def test_llm_error_stream_emits_error_event(self, test_client):
        """TC-S06: When LLM raises during stream, an error SSE event is emitted."""
        original_stream = fake_llm_singleton.chat_stream

        async def _raise_stream(*args, **kwargs):
            raise RuntimeError("Simulated timeout")
            yield  # make it a generator  # noqa: E702

        fake_llm_singleton.chat_stream = _raise_stream
        try:
            resp = test_client.post("/api/summary/generate", json={
                "thread_id": "sg-err-sse-1",
                "title": "Stream error",
                "content": "内容" * 10,
                "stream": True,
                "auto_tags": False,
            })
            assert resp.status_code == 200
            events = _parse_sse(resp.text)
            types = [e["type"] for e in events]
            assert "error" in types
        finally:
            fake_llm_singleton.chat_stream = original_stream


def _parse_sse(body: str):
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            raw = line[6:].strip()
            if raw:
                events.append(json.loads(raw))
    return events
