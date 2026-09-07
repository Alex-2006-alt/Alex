"""
ALEX — Long-Term Memory
Persistent memory across sessions using SQLite + vector similarity search.
Remembers user facts, preferences, past tasks, and entities.
"""

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from utils.logger import log
import config


@dataclass
class Fact:
    """A stored fact about the user or world."""
    id: int
    key: str
    value: str
    category: str = "general"
    confidence: float = 1.0
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0

    def __str__(self):
        return f"{self.key}: {self.value}"


class LongTermMemory:
    """
    Persistent long-term memory for Alex.

    Stores:
      - facts: Key-value facts about the user ("user's name is Sam")
      - tasks: History of completed/failed tasks
      - preferences: User preferences learned from interactions

    Uses sentence-transformers for semantic search if available,
    falls back to keyword search.
    """

    # Patterns to extract facts from conversation
    FACT_PATTERNS = [
        (r"my name is (\w+)", "user_name", "identity"),
        (r"i(?:'m| am) (\w+)", "user_name", "identity"),
        (r"call me (\w+)", "user_name", "identity"),
        (r"my email(?: is| address is)? ([\w.@]+)", "user_email", "contact"),
        (r"i(?:'m| am) (\d+) years? old", "user_age", "identity"),
        (r"i(?:'m| am) from ([\w\s]+)", "user_location", "identity"),
        (r"i live in ([\w\s]+)", "user_location", "identity"),
        (r"i work (?:at|for) ([\w\s]+)", "user_employer", "work"),
        (r"i(?:'m| am) a[n]? ([\w\s]+)", "user_occupation", "work"),
        (r"i prefer ([\w\s]+)", "user_preference", "preferences"),
        (r"i like ([\w\s]+)", "user_likes", "preferences"),
        (r"i (?:don't|do not) like ([\w\s]+)", "user_dislikes", "preferences"),
        (r"my (?:favorite|favourite) ([\w]+) is ([\w\s]+)", "user_favorite", "preferences"),
        (r"remind me (?:every|to) ([\w\s]+)", "user_reminder_pref", "preferences"),
    ]

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(config.MEMORY_DB_PATH)
        self._conn: sqlite3.Connection | None = None
        self._embedder = None
        self._embeddings_cache: dict[int, list[float]] = {}

        self._init_db()
        self._try_load_embedder()

        log.info(f"💾 Long-term memory initialized at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                confidence REAL DEFAULT 1.0,
                created_at REAL NOT NULL,
                last_accessed REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                UNIQUE(key)
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                status TEXT NOT NULL,
                steps_json TEXT,
                result TEXT,
                created_at REAL NOT NULL,
                finished_at REAL
            );

            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                attributes_json TEXT,
                created_at REAL NOT NULL,
                UNIQUE(name, entity_type)
            );

            CREATE TABLE IF NOT EXISTS conversation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp REAL NOT NULL,
                session_id TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
            CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        """)
        conn.commit()

    def _try_load_embedder(self):
        """Try to load sentence-transformers for semantic search."""
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
            log.info("✅ Semantic embedder loaded (sentence-transformers)")
        except ImportError:
            log.info("ℹ️ sentence-transformers not installed, using keyword search")
            self._embedder = None

    # ─── FACTS ───────────────────────────────────────────────────────────────

    def remember(self, key: str, value: str, category: str = "general", confidence: float = 1.0):
        """Store or update a fact."""
        now = time.time()
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO facts (key, value, category, confidence, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                category=excluded.category,
                confidence=excluded.confidence,
                last_accessed=excluded.last_accessed
        """, (key, value, category, confidence, now, now))
        conn.commit()
        log.info(f"💡 Remembered: {key} = {value}")

    def recall(self, query: str, category: str | None = None, top_k: int = 5) -> list[Fact]:
        """
        Retrieve relevant facts using semantic or keyword search.

        Args:
            query: Search query
            category: Optional category filter
            top_k: Maximum facts to return
        """
        conn = self._get_conn()

        if category:
            rows = conn.execute(
                "SELECT * FROM facts WHERE category=? ORDER BY last_accessed DESC LIMIT ?",
                (category, top_k * 3)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM facts ORDER BY access_count DESC, last_accessed DESC LIMIT ?",
                (top_k * 3,)
            ).fetchall()

        facts = [self._row_to_fact(r) for r in rows]

        if not facts:
            return []

        # Semantic re-ranking if embedder available
        if self._embedder and facts:
            query_emb = self._embedder.encode(query)
            scored = []
            for fact in facts:
                fact_text = f"{fact.key}: {fact.value}"
                fact_emb = self._embedder.encode(fact_text)
                score = self._cosine_similarity(query_emb, fact_emb)
                scored.append((score, fact))
            scored.sort(key=lambda x: x[0], reverse=True)
            facts = [f for _, f in scored[:top_k]]
        else:
            # Keyword fallback
            query_lower = query.lower()
            keywords = set(query_lower.split())
            scored = []
            for fact in facts:
                fact_text = (fact.key + " " + fact.value).lower()
                score = sum(1 for kw in keywords if kw in fact_text)
                scored.append((score, fact))
            scored.sort(key=lambda x: x[0], reverse=True)
            facts = [f for _, f in scored[:top_k] if _[0] > 0]

        # Update access counts
        for fact in facts:
            conn.execute(
                "UPDATE facts SET access_count=access_count+1, last_accessed=? WHERE id=?",
                (time.time(), fact.id)
            )
        conn.commit()

        return facts

    def forget(self, key: str) -> bool:
        """Delete a fact by key."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM facts WHERE key=?", (key,))
        conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            log.info(f"🗑️ Forgot: {key}")
        return deleted

    def get_all_facts(self, category: str | None = None) -> list[Fact]:
        """Get all stored facts, optionally filtered by category."""
        conn = self._get_conn()
        if category:
            rows = conn.execute("SELECT * FROM facts WHERE category=? ORDER BY key", (category,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM facts ORDER BY category, key").fetchall()
        return [self._row_to_fact(r) for r in rows]

    def get_user_profile(self) -> dict[str, str]:
        """Get a summary of what Alex knows about the user."""
        facts = self.get_all_facts(category="identity")
        facts += self.get_all_facts(category="contact")
        facts += self.get_all_facts(category="preferences")
        return {f.key: f.value for f in facts}

    def get_memory_prompt(self, query: str = "") -> str:
        """
        Get a memory context string to inject into the LLM prompt.
        """
        if query:
            facts = self.recall(query, top_k=8)
        else:
            facts = self.get_all_facts()[:10]

        if not facts:
            return ""

        lines = ["[MEMORY — What you know about the user:]"]
        for f in facts:
            lines.append(f"  - {f.key}: {f.value}")
        return "\n".join(lines)

    # ─── AUTO FACT EXTRACTION ─────────────────────────────────────────────────

    def extract_facts_from_text(self, text: str):
        """
        Automatically extract and store facts from user text.
        Called after each user input.
        """
        text_lower = text.lower()

        for pattern, key, category in self.FACT_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groups()
                value = " ".join(g for g in groups if g).strip()
                if value and len(value) > 1:
                    self.remember(key, value, category=category, confidence=0.9)

    # ─── TASK HISTORY ────────────────────────────────────────────────────────

    def save_task(self, goal: str, status: str, steps: list | None = None, result: str = "") -> int:
        """Save a completed or failed task to history."""
        conn = self._get_conn()
        cursor = conn.execute("""
            INSERT INTO tasks (goal, status, steps_json, result, created_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            goal,
            status,
            json.dumps(steps or []),
            result,
            time.time(),
            time.time(),
        ))
        conn.commit()
        return cursor.lastrowid

    def get_task_history(self, limit: int = 10) -> list[dict]:
        """Get recent task history."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, goal, status, result, created_at FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── CONVERSATION LOG ────────────────────────────────────────────────────

    def log_conversation(self, role: str, content: str, session_id: str = ""):
        """Persist a conversation message."""
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO conversation_log (role, content, timestamp, session_id) VALUES (?, ?, ?, ?)",
            (role, content, time.time(), session_id)
        )
        conn.commit()

    def get_recent_conversation(self, limit: int = 20, session_id: str = "") -> list[dict]:
        """Get recent conversation messages."""
        conn = self._get_conn()
        if session_id:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM conversation_log WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT role, content, timestamp FROM conversation_log ORDER BY timestamp DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def search_conversation(self, query: str, limit: int = 10) -> list[dict]:
        """
        Substring search over the conversation log, newest first.
        Folded in from the retired memory/storage.py.
        """
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content, timestamp FROM conversation_log "
            "WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
            (f"%{query}%", limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── HELPERS ─────────────────────────────────────────────────────────────

    def _row_to_fact(self, row: sqlite3.Row) -> Fact:
        return Fact(
            id=row["id"],
            key=row["key"],
            value=row["value"],
            category=row["category"],
            confidence=row["confidence"],
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
            access_count=row["access_count"],
        )

    def _cosine_similarity(self, a: list, b: list) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def stats(self) -> dict:
        """Return memory statistics."""
        conn = self._get_conn()
        fact_count = conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        convo_count = conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        return {
            "facts": fact_count,
            "tasks": task_count,
            "conversation_messages": convo_count,
            "semantic_search": self._embedder is not None,
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
