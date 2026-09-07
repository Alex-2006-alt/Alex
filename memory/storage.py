"""
ALEX — Persistent Storage
SQLite-based memory for conversation history, preferences, and learned patterns.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

from utils.logger import log
import config


class Storage:
    """SQLite-backed persistent storage for ALEX."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = str(db_path or config.MEMORY_DB_PATH)
        self._ensure_tables()
        log.info(f"💾 Storage initialized: {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    action TEXT,
                    action_params TEXT
                );

                CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message TEXT NOT NULL,
                    trigger_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS command_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    command TEXT NOT NULL,
                    action TEXT,
                    success INTEGER DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversations(timestamp);
                CREATE INDEX IF NOT EXISTS idx_reminders_trigger ON reminders(trigger_at);
            """)

    # ─── Conversation History ────────────────────────────────────────────────

    def save_message(self, role: str, content: str, action: str = None, action_params: dict = None):
        """Save a conversation message."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO conversations (timestamp, role, content, action, action_params) VALUES (?, ?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    role,
                    content,
                    action,
                    json.dumps(action_params) if action_params else None,
                ),
            )

    def get_recent_messages(self, limit: int = 20) -> list[dict]:
        """Get the most recent conversation messages."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [dict(row) for row in reversed(rows)]

    def search_conversations(self, query: str, limit: int = 10) -> list[dict]:
        """Search conversation history."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conversations WHERE content LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ─── User Preferences ───────────────────────────────────────────────────

    def set_preference(self, key: str, value: str):
        """Save a user preference."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().isoformat()),
            )

    def get_preference(self, key: str, default: str = None) -> str | None:
        """Get a user preference."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM preferences WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def get_all_preferences(self) -> dict:
        """Get all user preferences."""
        with self._get_conn() as conn:
            rows = conn.execute("SELECT key, value FROM preferences").fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ─── Reminders ───────────────────────────────────────────────────────────

    def add_reminder(self, message: str, trigger_at: datetime) -> int:
        """Add a reminder. Returns the reminder ID."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO reminders (message, trigger_at, created_at) VALUES (?, ?, ?)",
                (message, trigger_at.isoformat(), datetime.now().isoformat()),
            )
            return cursor.lastrowid

    def get_due_reminders(self) -> list[dict]:
        """Get all reminders that are due."""
        now = datetime.now().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM reminders WHERE trigger_at <= ? AND completed = 0",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def complete_reminder(self, reminder_id: int):
        """Mark a reminder as completed."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE reminders SET completed = 1 WHERE id = ?",
                (reminder_id,),
            )

    # ─── Command History ────────────────────────────────────────────────────

    def log_command(self, command: str, action: str = None, success: bool = True):
        """Log a command execution."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO command_history (timestamp, command, action, success) VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(), command, action, int(success)),
            )

    def get_frequent_commands(self, limit: int = 10) -> list[dict]:
        """Get most frequently used commands."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT command, action, COUNT(*) as count 
                   FROM command_history 
                   GROUP BY command 
                   ORDER BY count DESC 
                   LIMIT ?""",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
