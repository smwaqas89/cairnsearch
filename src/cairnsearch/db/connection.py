"""Database connection management."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from cairnsearch.config import get_config


def get_schema() -> str:
    """Load SQL schema from file."""
    schema_path = Path(__file__).parent / "schema.sql"
    return schema_path.read_text()


def init_db(db_path: Path | None = None) -> None:
    """Initialize database with schema."""
    if db_path is None:
        db_path = get_config().get_db_path()
    
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    conn.executescript(get_schema())
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()


@contextmanager
def get_connection(db_path: Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Get database connection context manager."""
    if db_path is None:
        db_path = get_config().get_db_path()
    
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


class Database:
    """Database helper class for common operations."""
    
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_config().get_db_path()
        init_db(self.db_path)
    
    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get connection context manager."""
        with get_connection(self.db_path) as conn:
            yield conn
    
    def execute(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Execute query and return results."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            return cursor.fetchall()
    
    def execute_write(self, query: str, params: tuple = ()) -> int:
        """Execute write query and return lastrowid."""
        with self.connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.lastrowid
    
    def executemany(self, query: str, params_list: list[tuple]) -> None:
        """Execute query with multiple parameter sets."""
        with self.connection() as conn:
            conn.executemany(query, params_list)
            conn.commit()
