"""L2 integration tests: LLM-backed paths via FakeLLM.

These cover the code paths that the existing test suite deliberately skipped
because they would otherwise call a real LLM provider. Every test here relies
on the autouse ``patch_llm_adapter`` fixture in ``conftest.py`` — no network
traffic, no api keys, no real OpenAI SDK construction.

Coverage map:
  * /api/summary/generate   — non-stream happy path + cache hit + regenerate
  * /api/summary/generate   — SSE stream happy path (parse events)
  * /api/tags/suggest       — AI-backed comma-separated parsing
  * /api/assist/polish      — 4 styles, content + length echo
  * /api/assist/format      — markdown/json/sql/python branches
  * /api/assist/check-code  — Line/severity regex parser
  * /api/assist/compare     — <TABLE>/<SUMMARY>/<RECOMMENDATION> parser

Also serves as the regression net for the L2 section of
docs/10-AUTO-TESTING.md.
"""

import json

import pytest

from tests.fake_llm import fake_llm_singleton, push_response


# ---------- Summary ----------------------------------------------------------


class TestSummaryWithLLM:
    """Summary generation paths that actually exercise llm.chat / chat_stream."""

    def test_generate_nonstream_happy(self, test_client):
        """TC-S01: non-stream generate returns summary + tags + tokens."""
        resp = test_client.post(
            "/api/summary/generate",
            json={
                "thread_id": "llm-int-1",
                "title": "A股动量策略回测",
                "content": "详细讨论了最近三年的动量因子在A股市场的表现和参数优化过程。" * 10,
                "stream": False,
                "auto_tags": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0, body
        data = body["data"]
        assert data["thread_id"] == "llm-int-1"
        assert data["summary"]  # non-empty
        assert data["tokens_used"] > 0
        # auto_tags is stored as a JSON string in the row — decode and check.
        tags = json.loads(data["auto_tags"]) if isinstance(data["auto_tags"], str) else data["auto_tags"]
        assert isinstance(tags, list)
        # FakeLLM returns "量化策略, 回测, 趋势跟踪" for tag prompts
        assert "量化策略" in tags

    def test_generate_cache_hit_skips_llm(self, test_client):
        """Second call with identical content should be a cache hit and not
        call the LLM again."""
        payload = {
            "thread_id": "llm-int-cache",
            "title": "Cache title",
            "content": "缓存测试的帖子内容" * 20,
            "stream": False,
            "auto_tags": False,
        }
        # Warm the cache.
        r1 = test_client.post("/api/summary/generate", json=payload)
        assert r1.json()["code"] == 0
        calls_after_first = fake_llm_singleton.calls

        # Hit again.
        r2 = test_client.post("/api/summary/generate", json=payload)
        assert r2.json()["code"] == 0
        # No additional chat() call — service returned the cached row.
        assert fake_llm_singleton.calls == calls_after_first

    def test_generate_regenerates_on_content_change(self, test_client):
        """Same thread_id but different content → content_hash diverges → new
        LLM call + UPDATE, not INSERT (would otherwise trip UNIQUE)."""
        # First version.
        test_client.post(
            "/api/summary/generate",
            json={
                "thread_id": "llm-int-regen",
                "title": "Old",
                "content": "版本一的内容",
                "stream": False,
                "auto_tags": False,
            },
        )
        calls_v1 = fake_llm_singleton.calls

        # Second version with changed content.
        r2 = test_client.post(
            "/api/summary/generate",
            json={
                "thread_id": "llm-int-regen",
                "title": "New",
                "content": "版本二的全新内容，与之前完全不同",
                "stream": False,
                "auto_tags": False,
            },
        )
        assert r2.json()["code"] == 0
        # LLM must have been called again.
        assert fake_llm_singleton.calls > calls_v1

        # And the DB row reflects the new title.
        get = test_client.get("/api/summary/llm-int-regen")
        assert get.json()["code"] == 0
        assert get.json()["data"]["title"] == "New"

    def test_generate_stream_emits_sse_events(self, test_client):
        """SSE stream emits chunk(s) → tags → done in order."""
        resp = test_client.post(
            "/api/summary/generate",
            json={
                "thread_id": "llm-int-sse",
                "title": "SSE test",
                "content": "SSE 流式测试内容" * 20,
                "stream": True,
                "auto_tags": True,
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "chunk" in types, types
        assert "tags" in types, types
        assert types[-1] == "done", types

        # Reassembled text should match what FakeLLM streamed (summary mode).
        full_text = "".join(e["text"] for e in events if e["type"] == "chunk")
        assert "量化策略" in full_text or "回测" in full_text or full_text  # non-empty at minimum

        # tags event actually carries a list
        tags_event = next(e for e in events if e["type"] == "tags")
        assert isinstance(tags_event["tags"], list)

        # done carries tokens_used
        done_event = next(e for e in events if e["type"] == "done")
        assert "tokens_used" in done_event

    def test_generate_stream_cached_path(self, test_client):
        """When cached, stream must not invoke chat_stream — it replays the
        cached summary as a single chunk + done with cached=True."""
        payload = {
            "thread_id": "llm-int-sse-cached",
            "title": "cached sse",
            "content": "先走非流式把缓存种上" * 5,
            "stream": False,
            "auto_tags": False,
        }
        # Prime cache via non-stream path.
        test_client.post("/api/summary/generate", json=payload)
        stream_calls_before = fake_llm_singleton.stream_calls

        # Now request stream for the same content.
        resp = test_client.post(
            "/api/summary/generate",
            json={**payload, "stream": True, "auto_tags": False},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        types = [e["type"] for e in events]
        assert "chunk" in types
        assert types[-1] == "done"
        # Cached path never calls chat_stream.
        assert fake_llm_singleton.stream_calls == stream_calls_before
        done = next(e for e in events if e["type"] == "done")
        assert done.get("cached") is True


def _parse_sse(body: str):
    """Return a list of decoded JSON payloads from an SSE response body."""
    events = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        raw = line[len("data: ") :].strip()
        if not raw:
            continue
        events.append(json.loads(raw))
    return events


# ---------- Tags -------------------------------------------------------------


class TestTagsWithLLM:
    def test_suggest_tags_returns_structured_list(self, test_client):
        """TC-T01: /api/tags/suggest returns non-empty list with name/category/confidence."""
        resp = test_client.post(
            "/api/tags/suggest",
            json={
                "content": "量化策略研究",
                "existing_tags": [],
                "max_suggestions": 3,
            },
        )
        assert resp.status_code == 200
        suggestions = resp.json()["data"]["suggested_tags"]
        assert len(suggestions) >= 1
        for s in suggestions:
            assert "name" in s and s["name"]
            assert "category" in s
            assert 0 < s["confidence"] <= 1

    def test_suggest_tags_ai_path(self, test_client):
        """TC-T02: /api/tags/suggest goes through LLM and parses comma list."""
        resp = test_client.post(
            "/api/tags/suggest",
            json={
                "content": "本文讨论了多因子选股策略的回测结果和夏普比率",
                "existing_tags": [],
                "max_suggestions": 5,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0, body
        suggestions = body["data"]["suggested_tags"]
        assert len(suggestions) >= 1
        names = [s["name"] for s in suggestions]
        # FakeLLM returns "量化策略, 回测, 趋势跟踪"
        assert "量化策略" in names
        assert "回测" in names
        # Confidence must be a float in (0, 1]
        assert all(0 < s["confidence"] <= 1 for s in suggestions)
        # Category must be inferred
        assert all("category" in s for s in suggestions)

    def test_suggest_tags_excludes_existing(self, test_client):
        """existing_tags should not appear in suggestions."""
        resp = test_client.post(
            "/api/tags/suggest",
            json={
                "content": "多因子选股和回测",
                "existing_tags": ["量化策略"],
                "max_suggestions": 5,
            },
        )
        body = resp.json()
        assert body["code"] == 0
        names = [s["name"] for s in body["data"]["suggested_tags"]]
        assert "量化策略" not in names
        assert "回测" in names  # still suggested


# ---------- Assist -----------------------------------------------------------


class TestAssistPolish:
    @pytest.mark.parametrize("style", ["professional", "casual", "academic", "concise"])
    def test_polish_all_styles(self, test_client, style):
        resp = test_client.post(
            "/api/assist/polish",
            json={"text": "原始文本内容", "style": style, "keep_length": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["result"]
        assert body["data"]["original_length"] == len("原始文本内容")
        assert body["data"]["style"] == style
        assert body["data"]["result_length"] == len(body["data"]["result"])


class TestAssistFormat:
    @pytest.mark.parametrize("fmt", ["markdown", "json", "sql", "python"])
    def test_format_all_types(self, test_client, fmt):
        resp = test_client.post(
            "/api/assist/format",
            json={"text": "some input", "format_type": fmt},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["format"] == fmt
        assert body["data"]["result"]


class TestAssistCheckCode:
    def test_check_code_parses_line_issues(self, test_client):
        """The route regex must pull 'Line N: [severity] msg' out of FakeLLM
        content and build structured issues."""
        resp = test_client.post(
            "/api/assist/check-code",
            json={"code": "def foo():\n    pass", "language": "python"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        issues = body["data"]["issues"]
        assert len(issues) >= 2
        # Every issue must have line + severity + message.
        for issue in issues:
            assert issue["line"] > 0
            assert issue["severity"] in {"error", "warning", "info"}
            assert issue["message"]
        severities = {i["severity"] for i in issues}
        # FakeLLM returns one warning + one error.
        assert "warning" in severities
        assert "error" in severities

    def test_check_code_no_issues_fallback(self, test_client):
        """When LLM returns no Line markers, route should fall back to a
        summary-of-raw-content path with an empty issues list."""
        push_response("Code looks fine. No structured issues to report.")
        resp = test_client.post(
            "/api/assist/check-code",
            json={"code": "x = 1", "language": "python"},
        )
        body = resp.json()
        assert body["code"] == 0
        assert body["data"]["issues"] == []
        assert body["data"]["summary"]  # non-empty fallback


class TestAssistCompare:
    def test_compare_parses_structured_sections(self, test_client):
        resp = test_client.post(
            "/api/assist/compare",
            json={
                "items": [
                    {"bookmark_id": "b1", "title": "动量策略", "summary": "夏普1.2"},
                    {"bookmark_id": "b2", "title": "回归策略", "summary": "夏普0.9"},
                ],
                "focus": "夏普比率",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        data = body["data"]
        # Parsed from <TABLE>/<SUMMARY>/<RECOMMENDATION> blocks.
        assert "|" in data["table"]  # markdown table survived
        assert data["summary"]
        assert data["recommendation"]

    def test_compare_three_items(self, test_client):
        """Route accepts up to 5 items; smoke-test the count path."""
        resp = test_client.post(
            "/api/assist/compare",
            json={
                "items": [
                    {"bookmark_id": "b1", "title": "A", "summary": "sa"},
                    {"bookmark_id": "b2", "title": "B", "summary": "sb"},
                    {"bookmark_id": "b3", "title": "C", "summary": "sc"},
                ]
            },
        )
        assert resp.json()["code"] == 0
