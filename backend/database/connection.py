"""Database connection management."""

import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from config import get_database_path


class DatabaseManager:
    """Async SQLite database manager."""
    
    _instance: Optional["DatabaseManager"] = None
    _pool: Optional[aiosqlite.Connection] = None
    
    def __new__(cls) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def initialize(self, db_path: Optional[Path] = None) -> None:
        """Initialize database connection pool."""
        if db_path is None:
            db_path = get_database_path()
        
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._pool = await aiosqlite.connect(
            str(db_path),
            detect_types=1,
            isolation_level=None  # Autocommit mode for simplicity
        )
        self._pool.row_factory = aiosqlite.Row
        
        # Enable foreign keys
        await self._pool.execute("PRAGMA foreign_keys = ON")
        # Enable WAL mode for better concurrency
        await self._pool.execute("PRAGMA journal_mode = WAL")
        await self._pool.execute("PRAGMA synchronous = NORMAL")
    
    async def close(self) -> None:
        """Close database connection."""
        if self._pool:
            await self._pool.close()
            self._pool = None
    
    @property
    def connection(self) -> aiosqlite.Connection:
        """Get database connection."""
        if self._pool is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._pool
    
    async def execute(self, sql: str, parameters: tuple = ()) -> aiosqlite.Cursor:
        """Execute SQL statement."""
        return await self.connection.execute(sql, parameters)
    
    async def executescript(self, sql: str) -> None:
        """Execute multiple SQL statements."""
        await self.connection.executescript(sql)

    async def executemany(self, sql: str, parameters: list) -> aiosqlite.Cursor:
        """Execute SQL statement multiple times."""
        return await self.connection.executemany(sql, parameters)
    
    async def fetchone(self, sql: str, parameters: tuple = ()) -> Optional[aiosqlite.Row]:
        """Fetch single row."""
        async with self.connection.execute(sql, parameters) as cursor:
            return await cursor.fetchone()
    
    async def fetchall(self, sql: str, parameters: tuple = ()) -> list:
        """Fetch all rows."""
        async with self.connection.execute(sql, parameters) as cursor:
            return await cursor.fetchall()
    
    async def fetchval(self, sql: str, parameters: tuple = ()) -> Optional[Any]:
        """Fetch single value."""
        row = await self.fetchone(sql, parameters)
        if row:
            return row[0]
        return None


# Global database manager instance
db = DatabaseManager()


@asynccontextmanager
async def get_db():
    """Get database connection context manager."""
    try:
        yield db.connection
    except Exception:
        await db.connection.rollback()
        raise


async def get_connection() -> aiosqlite.Connection:
    """Get database connection (for dependency injection)."""
    return db.connection
