"""Shared test fixtures and configuration."""

import os
import sys
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Use a temporary database for tests. Also create the knowledge/ subdirectories
# so that md_storage.save_md() can write files during test runs.
_test_db_dir = tempfile.mkdtemp()
# QUANTCLASS_HOME controls EVERYTHING: config.yaml path, data dir, md files.
# Without this, tests like test_update_default_model were overwriting the
# real user's ~/.quantclass/config.yaml because get_config_path() used to
# hard-code Path.home() / ".quantclass" / "config.yaml". This escape hatch
# is the reason config.py::_quantclass_home() exists.
os.environ["QUANTCLASS_HOME"] = _test_db_dir
os.environ["QUANTCLASS_DATA_DIR"] = os.path.join(_test_db_dir, "data")
os.environ["QUANTCLASS_ADMIN_PASSWORD"] = "admin123"  # Fixed password for test reproducibility
os.makedirs(os.path.join(_test_db_dir, "knowledge", "summaries"), exist_ok=True)
os.makedirs(os.path.join(_test_db_dir, "knowledge", "posts"), exist_ok=True)


# NOTE: we used to define a custom session-scoped `event_loop` fixture here,
# which triggered a deprecation warning under pytest-asyncio 0.24+ and was
# never actually entered by any test (coverage showed the body as dead). The
# loop scope is now driven by `asyncio_default_fixture_loop_scope = "session"`
# in pyproject.toml, which is the officially supported knob.


@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """Initialize test database."""
    from config import _config
    import config as cfg
    # Reset config singleton to pick up test env
    cfg._config = None

    from database.init_db import init_database, close_database
    db_path = Path(_test_db_dir) / "test.db"
    await init_database(db_path)
    yield
    await close_database()


@pytest.fixture(scope="session")
def test_client(setup_db, patch_llm_adapter):
    """Create a FastAPI test client."""
    # Must import after DB setup
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)
    return client


# ---------------------------------------------------------------------------
# LLM isolation (L2 invariant: no test ever hits a real LLM provider).
#
# See docs/10-AUTO-TESTING.md §3. Every caller of ``llm_adapter.get_llm()`` in
# the codebase receives the same FakeLLM instance, which returns deterministic
# prompt-aware content. Tests that need specific content can push onto the
# module-level queue via ``fake_llm.push_response``.
#
# Wired as autouse + session scope so it survives across the session-scoped
# ``test_client`` fixture. We replace the bound method on the singleton
# instance; ``monkeypatch`` is function-scoped and can't reach here.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def patch_llm_adapter(setup_db):
    """Replace ``llm_adapter.get_llm`` with a FakeLLM factory for all tests."""
    from llm import adapter
    from tests.fake_llm import fake_llm_singleton

    original = adapter.llm_adapter.get_llm

    def _fake_get_llm(provider=None, model=None):  # noqa: ARG001
        return fake_llm_singleton

    adapter.llm_adapter.get_llm = _fake_get_llm  # type: ignore[assignment]
    yield fake_llm_singleton
    adapter.llm_adapter.get_llm = original  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def reset_fake_llm_state():
    """Reset FakeLLM counters and queued responses between tests."""
    from tests.fake_llm import fake_llm_singleton, clear_queue

    fake_llm_singleton.calls = 0
    fake_llm_singleton.stream_calls = 0
    clear_queue()
    yield
    clear_queue()
