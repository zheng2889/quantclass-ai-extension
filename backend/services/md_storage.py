"""File-based Markdown storage for knowledge base content.

Instead of storing large text blobs (AI summaries, full post content)
directly in SQLite TEXT columns, we write them as individual ``.md``
files under ``{data_dir}/knowledge/`` and store the *relative path*
in the database. This makes the knowledge base browsable with any
editor / VS Code / git, and keeps the SQLite file lean.

Backward compatibility: ``resolve_content()`` detects whether a DB
value is a ``knowledge/`` path or inline text (from before this
migration) and does the right thing in either case.
"""

import logging
from pathlib import Path
from typing import Optional

from config import get_data_dir

logger = logging.getLogger(__name__)

KNOWLEDGE_DIR = "knowledge"
CATEGORIES = ("summaries", "posts")


def ensure_knowledge_dirs() -> Path:
    """Create ``{data_dir}/knowledge/{summaries,posts}/`` directories.

    Safe to call multiple times (``exist_ok=True``). Called once from
    ``main.py`` lifespan so the dirs are guaranteed to exist before
    any request handler runs.
    """
    base = get_data_dir() / KNOWLEDGE_DIR
    for cat in CATEGORIES:
        (base / cat).mkdir(parents=True, exist_ok=True)
    return base


def save_md(category: str, thread_id: str, content: str) -> str:
    """Write *content* to ``{data_dir}/knowledge/{category}/{thread_id}.md``.

    Returns the **relative path** (e.g. ``knowledge/summaries/77906.md``)
    which is what gets stored in the database column.
    """
    base = get_data_dir() / KNOWLEDGE_DIR
    path = base / category / f"{thread_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"{KNOWLEDGE_DIR}/{category}/{thread_id}.md"


def load_md(relative_path: str) -> Optional[str]:
    """Read content from a *relative_path* under ``data_dir``.

    Returns ``None`` if the file doesn't exist so callers can fall back
    gracefully (e.g. show ``[File not found]`` in the UI).
    """
    full = get_data_dir() / relative_path
    if full.is_file():
        return full.read_text(encoding="utf-8")
    logger.warning("MD file not found: %s", full)
    return None


def delete_md(relative_path: str) -> None:
    """Delete a ``.md`` file. Silently ignores if already missing."""
    if not relative_path or not relative_path.startswith(KNOWLEDGE_DIR):
        return
    full = get_data_dir() / relative_path
    try:
        full.unlink(missing_ok=True)
    except Exception as e:
        logger.warning("Failed to delete MD file %s: %s", full, e)


def resolve_content(db_value: Optional[str]) -> str:
    """Transparently resolve a DB column that might be either:

    - A ``knowledge/…`` relative path (new format) → read file content.
    - Inline text (legacy format, pre-migration) → return as-is.
    - ``None`` / empty → return empty string.

    Every read-path in summary_service / knowledge_service should call
    this instead of using the raw DB value, so old and new data coexist.
    """
    if not db_value:
        return ""
    if db_value.startswith(f"{KNOWLEDGE_DIR}/"):
        content = load_md(db_value)
        if content is not None:
            return content
        return f"[File not found: {db_value}]"
    # Legacy inline text — return as-is.
    return db_value
