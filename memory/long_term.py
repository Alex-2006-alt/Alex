"""
ALEX — Long-Term Memory (Unified Learning System)
Persistent memory across sessions using SQLite + vector similarity search.
Remembers user facts, preferences, past tasks, entities, and learned workflows.

Learning subsystems:
  1. Continuous LLM-powered fact & preference extraction
  2. Feedback/correction reinforcement with confidence decay
  3. Workflow/macro learning from successful multi-step plans
"""

import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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
        self._db_lock = threading.Lock()  # Protects concurrent thread access

        self._init_db()
        self._try_load_embedder()

        log.info(f"💾 Long-term memory initialized at {self.db_path}")

    def _get_conn(self) -> sqlite3.Connection:
        with self._db_lock:
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
                source TEXT DEFAULT 'regex',
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

            CREATE TABLE IF NOT EXISTS learned_workflows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal_pattern TEXT NOT NULL,
                steps_json TEXT NOT NULL,
                success_count INTEGER DEFAULT 1,
                fail_count INTEGER DEFAULT 0,
                last_used REAL NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS preference_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger TEXT NOT NULL,
                action TEXT NOT NULL,
                params_json TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                use_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                last_used REAL NOT NULL,
                UNIQUE(trigger)
            );

            CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key);
            CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_workflows_goal ON learned_workflows(goal_pattern);
            CREATE INDEX IF NOT EXISTS idx_pref_trigger ON preference_rules(trigger);
        """)
        conn.commit()

        # Schema migration: add 'source' column to facts if missing (existing DBs)
        try:
            conn.execute("SELECT source FROM facts LIMIT 1")
        except sqlite3.OperationalError:
            conn.execute("ALTER TABLE facts ADD COLUMN source TEXT DEFAULT 'regex'")
            conn.commit()
            log.info("📦 Migrated facts table: added 'source' column")

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

    def remember(self, key: str, value: str, category: str = "general",
                 confidence: float = 1.0, source: str = "regex"):
        """Store or update a fact."""
        now = time.time()
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO facts (key, value, category, confidence, source, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                category=excluded.category,
                confidence=excluded.confidence,
                source=excluded.source,
                last_accessed=excluded.last_accessed
        """, (key, value, category, confidence, source, now, now))
        conn.commit()
        log.info(f"💡 Remembered [{source}]: {key} = {value}")

    def forget(self, key: str) -> bool:
        """Delete a fact by its exact key."""
        conn = self._get_conn()
        cursor = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
        conn.commit()
        if cursor.rowcount > 0:
            log.info(f"🗑️ Forgot fact: {key}")
            return True
        return False

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
            facts = [f for _, f in scored[:top_k] if _ > 0]

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
        Automatically extract and store facts from user text using regex patterns.
        Called after each user input. For deeper extraction, use learn_from_interaction().
        """
        text_lower = text.lower()

        for pattern, key, category in self.FACT_PATTERNS:
            match = re.search(pattern, text_lower)
            if match:
                groups = match.groups()
                value = " ".join(g for g in groups if g).strip()
                if value and len(value) > 1:
                    self.remember(key, value, category=category, confidence=0.9, source="regex")

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

    # ─── UNIFIED LEARNING SYSTEM ─────────────────────────────────────────────

    # System prompt sent to the local LLM for reflection-based learning.
    _LEARNING_PROMPT = """You are a memory extraction system for a personal AI assistant.
Analyze this conversation turn and extract structured knowledge.

User said: {user_text}
Assistant replied: {assistant_text}

Extract ANY of the following (return ONLY valid JSON, no other text):
{{
  "facts": [
    {{"key": "unique_key", "value": "what to remember", "category": "identity|contact|preferences|work|system|general", "confidence": 0.8}}
  ],
  "corrections": [
    {{"old_key": "key being corrected", "new_value": "corrected value", "reason": "why"}}
  ],
  "preference_rules": [
    {{"trigger": "when user says X", "action": "tool_name", "params": {{}}}}
  ]
}}

RULES:
- Extract IMPLICIT facts too (e.g. "open my project" implies they have a project)
- Detect corrections: "no", "actually", "not that", "I meant", "change to", "use X instead"
- Detect preferences: "always use", "I prefer", "never", "default to", "don't use"
- If nothing to extract, return {{"facts": [], "corrections": [], "preference_rules": []}}
- Keep keys lowercase_with_underscores
- Confidence: 0.9 for explicit statements, 0.7 for implicit, 0.5 for guesses
"""

    # Phrases that signal the user is correcting Alex.
    _CORRECTION_SIGNALS = [
        "no,", "no ", "not that", "actually", "i meant", "i said",
        "that's wrong", "that's not", "change to", "change it to",
        "use .* instead", "don't use", "do not use", "stop using",
        "switch to", "i prefer", "i told you", "remember that",
        "wrong", "incorrect", "never",
    ]
    _CORRECTION_RE = re.compile(
        "|".join(_CORRECTION_SIGNALS), re.IGNORECASE
    )

    def learn_from_interaction(
        self,
        user_text: str,
        assistant_text: str,
        llm_caller: Callable[[str], str],
    ):
        """
        Run LLM-powered reflection on a conversation turn to extract
        facts, corrections, and preference rules. Runs asynchronously
        in a background thread so it never blocks the conversation.

        Args:
            user_text: What the user said.
            assistant_text: What Alex replied.
            llm_caller: Function(prompt) -> str that calls the local LLM.
        """
        def _learn():
            try:
                self._learn_sync(user_text, assistant_text, llm_caller)
            except Exception as e:
                log.warning(f"🧠 Background learning failed (non-fatal): {e}")

        thread = threading.Thread(target=_learn, daemon=True, name="alex-learner")
        thread.start()

    def _learn_sync(
        self,
        user_text: str,
        assistant_text: str,
        llm_caller: Callable[[str], str],
    ):
        """Synchronous learning — called inside the background thread."""
        # Step 1: Quick heuristic correction detection (no LLM needed)
        if self._CORRECTION_RE.search(user_text):
            self._handle_correction_heuristic(user_text)

        # Step 2: LLM-powered deep extraction
        prompt = self._LEARNING_PROMPT.format(
            user_text=user_text,
            assistant_text=assistant_text[:500],  # Truncate long replies
        )

        try:
            raw = llm_caller(prompt)
            data = self._parse_learning_json(raw)
            if not data:
                return
        except Exception as e:
            log.debug(f"Learning LLM call failed: {e}")
            return

        # Process extracted facts
        for fact in data.get("facts", []):
            key = fact.get("key", "").strip().lower()
            value = str(fact.get("value", "")).strip().lower()
            if key and value and len(value) > 1 and key not in ("none", "null") and value not in ("none", "null"):
                self.remember(
                    key=key,
                    value=fact.get("value", "").strip(),  # preserve original case for value
                    category=fact.get("category", "general"),
                    confidence=min(fact.get("confidence", 0.7), 1.0),
                    source="llm",
                )

        # Process corrections
        for correction in data.get("corrections", []):
            old_key = correction.get("old_key", "").strip()
            new_value = correction.get("new_value", "").strip()
            if old_key and new_value:
                self._apply_correction(old_key, new_value)

        # Process preference rules
        for rule in data.get("preference_rules", []):
            trigger = rule.get("trigger", "").strip()
            action = rule.get("action", "").strip()
            if trigger and action:
                self._save_preference_rule(
                    trigger=trigger,
                    action=action,
                    params=rule.get("params", {}),
                )

        extracted = (
            len(data.get("facts", []))
            + len(data.get("corrections", []))
            + len(data.get("preference_rules", []))
        )
        if extracted:
            log.info(f"🧠 Learned {extracted} item(s) from interaction")

    def _parse_learning_json(self, raw: str) -> dict | None:
        """Extract JSON from LLM learning response."""
        # Try direct parse
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # Try code-fence extraction
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
        if fence:
            try:
                return json.loads(fence.group(1).strip())
            except json.JSONDecodeError:
                pass
        # Try brace extraction
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end])
            except json.JSONDecodeError:
                pass
        return None

    # ─── FEEDBACK / CORRECTION REINFORCEMENT ─────────────────────────────────

    def _handle_correction_heuristic(self, user_text: str):
        """
        Quick regex-based correction handler. Catches patterns like:
          - "use Firefox instead of Chrome"
          - "no, my name is Sam"
          - "actually I prefer dark mode"
        Demotes confidence of contradicted facts.
        """
        # "use X instead of Y" pattern
        instead = re.search(
            r"(?:use|switch to|prefer)\s+(.+?)\s+instead\s+of\s+(.+)",
            user_text, re.IGNORECASE,
        )
        if instead:
            new_val = instead.group(1).strip()
            old_val = instead.group(2).strip()
            self._demote_facts_containing(old_val)
            log.info(f"🔄 Correction detected: '{old_val}' → '{new_val}'")

    def _apply_correction(self, old_key: str, new_value: str):
        """Update a fact identified by the LLM as needing correction."""
        conn = self._get_conn()
        # Check if the fact exists
        row = conn.execute("SELECT * FROM facts WHERE key = ?", (old_key,)).fetchone()
        if row:
            conn.execute(
                "UPDATE facts SET value = ?, confidence = 1.0, source = 'correction', last_accessed = ? WHERE key = ?",
                (new_value, time.time(), old_key),
            )
            conn.commit()
            log.info(f"🔄 Corrected: {old_key} → {new_value}")
        else:
            # Store as new fact with high confidence
            self.remember(old_key, new_value, category="preferences", confidence=1.0, source="correction")

    def _demote_facts_containing(self, substring: str):
        """Reduce confidence of facts whose value contains the given substring."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, key, value, confidence FROM facts WHERE LOWER(value) LIKE ?",
            (f"%{substring.lower()}%",),
        ).fetchall()
        for row in rows:
            new_conf = max(row["confidence"] * 0.5, 0.1)  # Halve, floor at 0.1
            conn.execute(
                "UPDATE facts SET confidence = ? WHERE id = ?",
                (new_conf, row["id"]),
            )
            log.info(f"📉 Demoted fact '{row['key']}' confidence → {new_conf:.2f}")
        conn.commit()

    def reinforce_fact(self, key: str, boost: float = 0.1):
        """Increase confidence of a fact that was successfully used."""
        conn = self._get_conn()
        conn.execute(
            "UPDATE facts SET confidence = MIN(confidence + ?, 1.0), "
            "access_count = access_count + 1, last_accessed = ? WHERE key = ?",
            (boost, time.time(), key),
        )
        conn.commit()

    def decay_stale_facts(self, days_threshold: int = 30, decay_rate: float = 0.05):
        """Periodically decay confidence of facts not accessed recently."""
        cutoff = time.time() - (days_threshold * 86400)
        conn = self._get_conn()
        conn.execute(
            "UPDATE facts SET confidence = MAX(confidence - ?, 0.1) "
            "WHERE last_accessed < ? AND source != 'correction'",
            (decay_rate, cutoff),
        )
        conn.commit()
        log.info(f"📉 Decayed stale facts older than {days_threshold} days")

    # ─── PREFERENCE RULES ────────────────────────────────────────────────────

    def _save_preference_rule(self, trigger: str, action: str, params: dict):
        """Save or update a learned preference rule."""
        now = time.time()
        conn = self._get_conn()
        conn.execute("""
            INSERT INTO preference_rules (trigger, action, params_json, confidence, use_count, created_at, last_used)
            VALUES (?, ?, ?, 0.8, 0, ?, ?)
            ON CONFLICT(trigger) DO UPDATE SET
                action=excluded.action,
                params_json=excluded.params_json,
                confidence = MIN(confidence + 0.1, 1.0),
                last_used=excluded.last_used
        """, (trigger, action, json.dumps(params), now, now))
        conn.commit()
        log.info(f"📌 Preference rule: '{trigger}' → {action}")

    def get_matching_preferences(self, user_input: str, top_k: int = 3) -> list[dict]:
        """Find preference rules that match the current user input."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM preference_rules ORDER BY confidence DESC, use_count DESC"
        ).fetchall()

        if not rows:
            return []

        input_lower = user_input.lower()
        matches = []
        for row in rows:
            trigger = row["trigger"].lower()
            # Simple substring match; semantic matching via embedder if available
            trigger_words = set(trigger.split())
            input_words = set(input_lower.split())
            overlap = len(trigger_words & input_words) / max(len(trigger_words), 1)
            if overlap >= 0.4:  # At least 40% keyword overlap
                matches.append({
                    "trigger": row["trigger"],
                    "action": row["action"],
                    "params": json.loads(row["params_json"]),
                    "confidence": row["confidence"],
                })

        return matches[:top_k]

    # ─── WORKFLOW / MACRO LEARNING ───────────────────────────────────────────

    def save_learned_workflow(self, goal: str, steps: list[dict]):
        """
        Save a successfully completed multi-step plan as a reusable workflow.
        If a similar goal already exists, increment its success_count.
        """
        now = time.time()
        conn = self._get_conn()

        # Normalize the goal for matching
        goal_pattern = self._normalize_goal(goal)

        existing = conn.execute(
            "SELECT id, success_count FROM learned_workflows WHERE goal_pattern = ?",
            (goal_pattern,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE learned_workflows SET success_count = success_count + 1, "
                "last_used = ?, steps_json = ? WHERE id = ?",
                (now, json.dumps(steps), existing["id"]),
            )
            log.info(f"📈 Workflow reinforced (×{existing['success_count'] + 1}): {goal_pattern[:60]}")
        else:
            conn.execute(
                "INSERT INTO learned_workflows (goal_pattern, steps_json, success_count, fail_count, last_used, created_at) "
                "VALUES (?, ?, 1, 0, ?, ?)",
                (goal_pattern, json.dumps(steps), now, now),
            )
            log.info(f"📖 New workflow learned: {goal_pattern[:60]}")

        conn.commit()

    def mark_workflow_failed(self, goal: str):
        """Record that a workflow for this goal failed."""
        goal_pattern = self._normalize_goal(goal)
        conn = self._get_conn()
        conn.execute(
            "UPDATE learned_workflows SET fail_count = fail_count + 1 WHERE goal_pattern = ?",
            (goal_pattern,),
        )
        conn.commit()

    def find_learned_workflow(self, goal: str, min_successes: int = 2) -> dict | None:
        """
        Find a previously learned workflow that matches the current goal.
        Only returns workflows with enough successful runs to be trustworthy.

        Args:
            goal: The user's current goal/request.
            min_successes: Minimum success count to consider a workflow reliable.

        Returns:
            dict with 'goal_pattern', 'steps', 'success_count' or None.
        """
        goal_pattern = self._normalize_goal(goal)
        conn = self._get_conn()

        # Exact match first
        row = conn.execute(
            "SELECT * FROM learned_workflows WHERE goal_pattern = ? "
            "AND success_count >= ? AND success_count > fail_count "
            "ORDER BY success_count DESC LIMIT 1",
            (goal_pattern, min_successes),
        ).fetchone()

        if row:
            return {
                "goal_pattern": row["goal_pattern"],
                "steps": json.loads(row["steps_json"]),
                "success_count": row["success_count"],
            }

        # Fuzzy keyword match if embedder is unavailable
        goal_words = set(goal_pattern.split())
        if len(goal_words) < 2:
            return None

        all_rows = conn.execute(
            "SELECT * FROM learned_workflows WHERE success_count >= ? "
            "AND success_count > fail_count ORDER BY success_count DESC LIMIT 50",
            (min_successes,),
        ).fetchall()

        best_match = None
        best_overlap = 0.0
        for r in all_rows:
            pattern_words = set(r["goal_pattern"].split())
            overlap = len(goal_words & pattern_words) / max(len(goal_words | pattern_words), 1)
            if overlap > best_overlap and overlap >= 0.6:  # 60% Jaccard threshold
                best_overlap = overlap
                best_match = r

        if best_match:
            return {
                "goal_pattern": best_match["goal_pattern"],
                "steps": json.loads(best_match["steps_json"]),
                "success_count": best_match["success_count"],
            }

        return None

    def get_all_workflows(self, limit: int = 20) -> list[dict]:
        """Return all learned workflows, most successful first."""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT goal_pattern, success_count, fail_count, last_used "
            "FROM learned_workflows ORDER BY success_count DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _normalize_goal(self, goal: str) -> str:
        """Normalize a goal string for matching: lowercase, strip noise words."""
        noise = {"please", "can", "you", "could", "would", "the", "a", "an",
                 "my", "me", "i", "to", "for", "and", "then", "also", "just"}
        words = goal.lower().split()
        return " ".join(w for w in words if w not in noise and len(w) > 1)

    # ─── ENHANCED MEMORY PROMPT ──────────────────────────────────────────────

    def get_memory_prompt(self, query: str = "") -> str:
        """
        Get a memory context string to inject into the LLM prompt.
        Now includes preference rules and high-confidence facts.
        """
        lines = []

        # High-confidence facts first
        if query:
            facts = self.recall(query, top_k=8)
        else:
            facts = self.get_all_facts()[:10]

        if facts:
            lines.append("[MEMORY — What you know about the user:]")
            for f in facts:
                conf_tag = "" if f.confidence >= 0.8 else f" (conf={f.confidence:.1f})"
                lines.append(f"  - {f.key}: {f.value}{conf_tag}")

        # Matching preference rules
        if query:
            prefs = self.get_matching_preferences(query, top_k=3)
            if prefs:
                lines.append("[LEARNED PREFERENCES:]")
                for p in prefs:
                    lines.append(f"  - When user says '{p['trigger']}' → use {p['action']}")

        if not lines:
            return ""
        return "\n".join(lines)

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
        workflow_count = conn.execute("SELECT COUNT(*) FROM learned_workflows").fetchone()[0]
        pref_count = conn.execute("SELECT COUNT(*) FROM preference_rules").fetchone()[0]
        return {
            "facts": fact_count,
            "tasks": task_count,
            "conversation_messages": convo_count,
            "learned_workflows": workflow_count,
            "preference_rules": pref_count,
            "semantic_search": self._embedder is not None,
        }

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
