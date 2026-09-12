"""
Tests for the Unified Learning System.

Covers:
  1. LLM-powered fact extraction (learn_from_interaction)
  2. Feedback/correction reinforcement (confidence decay, overwrite)
  3. Workflow/macro learning (save, recall, fuzzy match)
  4. Preference rule detection and matching
"""

import json
import sqlite3
import time
import pytest
from unittest.mock import MagicMock

# Ensure the project root is on sys.path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.long_term import LongTermMemory


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def mem(tmp_path):
    """Fresh in-memory LongTermMemory for each test."""
    db_path = str(tmp_path / "test_memory.db")
    m = LongTermMemory(db_path=db_path)
    return m


def _mock_llm(response_json: dict):
    """Return a mock LLM caller that always returns the given JSON."""
    def caller(prompt: str) -> str:
        return json.dumps(response_json)
    return caller


# ─── 1. LLM-Powered Fact Extraction ─────────────────────────────────────────


class TestLLMFactExtraction:

    def test_extracts_explicit_fact(self, mem: LongTermMemory):
        """LLM extraction stores a fact from natural language."""
        llm = _mock_llm({
            "facts": [
                {"key": "user_name", "value": "Sam", "category": "identity", "confidence": 0.9}
            ],
            "corrections": [],
            "preference_rules": [],
        })

        mem._learn_sync("My name is Sam", "Nice to meet you, Sam!", llm)

        facts = mem.get_all_facts()
        assert any(f.key == "user_name" and f.value == "Sam" for f in facts)

    def test_extracts_implicit_fact(self, mem: LongTermMemory):
        """LLM extraction catches implicit information."""
        llm = _mock_llm({
            "facts": [
                {"key": "user_project_dir", "value": "E:\\projects", "category": "system", "confidence": 0.7}
            ],
            "corrections": [],
            "preference_rules": [],
        })

        mem._learn_sync("Open my project from E:\\projects", "Opening...", llm)

        facts = mem.get_all_facts()
        assert any(f.key == "user_project_dir" for f in facts)
        proj = [f for f in facts if f.key == "user_project_dir"][0]
        assert proj.confidence == 0.7

    def test_extracts_multiple_items(self, mem: LongTermMemory):
        """LLM returns multiple facts + a preference rule."""
        llm = _mock_llm({
            "facts": [
                {"key": "user_name", "value": "Sam", "category": "identity", "confidence": 0.9},
                {"key": "user_browser", "value": "Firefox", "category": "preferences", "confidence": 0.8},
            ],
            "corrections": [],
            "preference_rules": [
                {"trigger": "open browser", "action": "open_app", "params": {"name": "firefox"}}
            ],
        })

        mem._learn_sync("I'm Sam and I always use Firefox", "Got it!", llm)

        facts = mem.get_all_facts()
        assert len(facts) >= 2
        prefs = mem.get_matching_preferences("open browser")
        assert len(prefs) >= 1
        assert prefs[0]["action"] == "open_app"

    def test_empty_extraction_is_harmless(self, mem: LongTermMemory):
        """LLM returns nothing to extract — no crash, no data."""
        llm = _mock_llm({
            "facts": [], "corrections": [], "preference_rules": [],
        })

        mem._learn_sync("how are you?", "I'm great!", llm)
        assert mem.get_all_facts() == []

    def test_llm_failure_is_non_fatal(self, mem: LongTermMemory):
        """If the LLM raises, learning silently fails."""
        def broken_llm(prompt: str) -> str:
            raise ConnectionError("model offline")

        # Should NOT raise
        mem._learn_sync("hello", "hi", broken_llm)
        assert mem.get_all_facts() == []

    def test_malformed_json_is_handled(self, mem: LongTermMemory):
        """LLM returns garbage — no crash."""
        def bad_json_llm(prompt: str) -> str:
            return "Sure! Here's what I found: not valid json at all"

        mem._learn_sync("test", "test", bad_json_llm)
        assert mem.get_all_facts() == []

    def test_source_field_set_to_llm(self, mem: LongTermMemory):
        """Facts from LLM extraction should be tagged with source='llm'."""
        llm = _mock_llm({
            "facts": [{"key": "fav_color", "value": "blue", "category": "preferences", "confidence": 0.8}],
            "corrections": [],
            "preference_rules": [],
        })

        mem._learn_sync("I love blue", "Noted!", llm)

        conn = mem._get_conn()
        row = conn.execute("SELECT source FROM facts WHERE key='fav_color'").fetchone()
        assert row["source"] == "llm"


# ─── 2. Feedback / Correction Reinforcement ─────────────────────────────────


class TestCorrectionReinforcement:

    def test_correction_overwrites_old_fact(self, mem: LongTermMemory):
        """LLM detects a correction and overwrites the old value."""
        mem.remember("user_browser", "Chrome", category="preferences", source="llm")

        llm = _mock_llm({
            "facts": [],
            "corrections": [
                {"old_key": "user_browser", "new_value": "Firefox", "reason": "user corrected"}
            ],
            "preference_rules": [],
        })

        mem._learn_sync("Actually, use Firefox instead", "Got it!", llm)

        facts = mem.get_all_facts()
        browser = [f for f in facts if f.key == "user_browser"][0]
        assert browser.value == "Firefox"
        assert browser.confidence == 1.0

    def test_heuristic_demotes_old_value(self, mem: LongTermMemory):
        """'use X instead of Y' heuristic demotes facts containing Y."""
        mem.remember("preferred_editor", "Notepad", category="preferences", confidence=0.9)

        mem._handle_correction_heuristic("use VSCode instead of Notepad")

        facts = mem.get_all_facts()
        editor = [f for f in facts if f.key == "preferred_editor"][0]
        assert editor.confidence < 0.5  # Halved from 0.9

    def test_reinforce_fact_boosts_confidence(self, mem: LongTermMemory):
        """reinforce_fact increases confidence up to 1.0."""
        mem.remember("user_lang", "Python", confidence=0.6)
        mem.reinforce_fact("user_lang", boost=0.2)

        facts = mem.get_all_facts()
        lang = [f for f in facts if f.key == "user_lang"][0]
        assert lang.confidence == pytest.approx(0.8, abs=0.01)

    def test_reinforce_caps_at_1(self, mem: LongTermMemory):
        """Reinforcement never exceeds 1.0."""
        mem.remember("test_key", "val", confidence=0.95)
        mem.reinforce_fact("test_key", boost=0.5)

        facts = mem.get_all_facts()
        f = [x for x in facts if x.key == "test_key"][0]
        assert f.confidence <= 1.0

    def test_decay_stale_facts(self, mem: LongTermMemory):
        """Stale facts have their confidence decayed."""
        # Insert a fact with old timestamp
        conn = mem._get_conn()
        old_time = time.time() - (60 * 86400)  # 60 days ago
        conn.execute(
            "INSERT INTO facts (key, value, category, confidence, source, created_at, last_accessed, access_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("old_fact", "old_value", "general", 0.8, "llm", old_time, old_time, 0),
        )
        conn.commit()

        mem.decay_stale_facts(days_threshold=30, decay_rate=0.2)

        row = conn.execute("SELECT confidence FROM facts WHERE key='old_fact'").fetchone()
        assert row[0] == pytest.approx(0.6, abs=0.01)

    def test_corrections_source_tagged(self, mem: LongTermMemory):
        """Corrected facts should have source='correction'."""
        mem.remember("user_city", "Mumbai", source="regex")
        mem._apply_correction("user_city", "Delhi")

        conn = mem._get_conn()
        row = conn.execute("SELECT source, value FROM facts WHERE key='user_city'").fetchone()
        assert row["source"] == "correction"
        assert row["value"] == "Delhi"


# ─── 3. Workflow / Macro Learning ────────────────────────────────────────────


class TestWorkflowLearning:

    def _sample_steps(self):
        return [
            {"id": 1, "action": "open_app", "params": {"name": "vscode"}, "description": "Open VS Code", "depends_on": []},
            {"id": 2, "action": "open_url", "params": {"url": "http://localhost:3000"}, "description": "Open dev server", "depends_on": [1]},
        ]

    def test_save_and_recall_workflow(self, mem: LongTermMemory):
        """A workflow saved 2+ times can be recalled."""
        steps = self._sample_steps()
        mem.save_learned_workflow("Open VS Code and then open browser to localhost", steps)
        mem.save_learned_workflow("Open VS Code and then open browser to localhost", steps)

        result = mem.find_learned_workflow("Open VS Code and then open browser to localhost")
        assert result is not None
        assert result["success_count"] >= 2
        assert len(result["steps"]) == 2

    def test_single_save_not_recalled(self, mem: LongTermMemory):
        """A workflow seen only once doesn't meet the min_successes threshold."""
        steps = self._sample_steps()
        mem.save_learned_workflow("One-off task", steps)

        result = mem.find_learned_workflow("One-off task", min_successes=2)
        assert result is None

    def test_fuzzy_goal_matching(self, mem: LongTermMemory):
        """Similar goals match via keyword overlap even if not identical."""
        steps = self._sample_steps()
        mem.save_learned_workflow("Open VS Code and open browser to localhost", steps)
        mem.save_learned_workflow("Open VS Code and open browser to localhost", steps)

        # Slightly different phrasing
        result = mem.find_learned_workflow("Please open VS Code and open browser localhost")
        assert result is not None

    def test_failed_workflow_not_recalled(self, mem: LongTermMemory):
        """A workflow with more failures than successes is not trusted."""
        steps = self._sample_steps()
        mem.save_learned_workflow("Flaky task", steps)
        mem.save_learned_workflow("Flaky task", steps)
        mem.mark_workflow_failed("Flaky task")
        mem.mark_workflow_failed("Flaky task")
        mem.mark_workflow_failed("Flaky task")  # 2 successes, 3 failures

        result = mem.find_learned_workflow("Flaky task")
        assert result is None

    def test_get_all_workflows(self, mem: LongTermMemory):
        """get_all_workflows returns stored workflows."""
        steps = self._sample_steps()
        mem.save_learned_workflow("Open vscode editor", steps)
        mem.save_learned_workflow("Search google web", steps)

        all_wf = mem.get_all_workflows()
        assert len(all_wf) == 2

    def test_normalize_goal_strips_noise(self, mem: LongTermMemory):
        """Goal normalization removes filler words."""
        n1 = mem._normalize_goal("Can you please open my browser for me")
        n2 = mem._normalize_goal("Open browser")
        # Both should reduce to similar core words
        assert "open" in n1
        assert "browser" in n1
        assert "please" not in n1
        assert "can" not in n1


# ─── 4. Preference Rules ────────────────────────────────────────────────────


class TestPreferenceRules:

    def test_save_and_match_preference(self, mem: LongTermMemory):
        """A saved preference rule can be matched by keyword overlap."""
        mem._save_preference_rule(
            trigger="open browser",
            action="open_app",
            params={"name": "firefox"},
        )

        matches = mem.get_matching_preferences("please open browser")
        assert len(matches) >= 1
        assert matches[0]["action"] == "open_app"
        assert matches[0]["params"]["name"] == "firefox"

    def test_no_match_for_unrelated_input(self, mem: LongTermMemory):
        """Preference rules don't match unrelated inputs."""
        mem._save_preference_rule(
            trigger="open browser",
            action="open_app",
            params={"name": "firefox"},
        )

        matches = mem.get_matching_preferences("what is the weather")
        assert len(matches) == 0

    def test_repeated_rule_increases_confidence(self, mem: LongTermMemory):
        """Saving the same trigger twice increases its confidence."""
        mem._save_preference_rule("play music", "open_app", {"name": "spotify"})
        mem._save_preference_rule("play music", "open_app", {"name": "spotify"})

        conn = mem._get_conn()
        row = conn.execute("SELECT confidence FROM preference_rules WHERE trigger='play music'").fetchone()
        assert row[0] > 0.8  # Started at 0.8, bumped by 0.1

    def test_memory_prompt_includes_preferences(self, mem: LongTermMemory):
        """get_memory_prompt includes matched preference rules."""
        mem._save_preference_rule("open browser", "open_app", {"name": "brave"})

        prompt = mem.get_memory_prompt("open browser for me")
        assert "LEARNED PREFERENCES" in prompt
        assert "open_app" in prompt


# ─── 5. Enhanced Memory Stats ────────────────────────────────────────────────


class TestMemoryStats:

    def test_stats_include_new_tables(self, mem: LongTermMemory):
        """stats() should report learned_workflows and preference_rules counts."""
        s = mem.stats()
        assert "learned_workflows" in s
        assert "preference_rules" in s
        assert s["learned_workflows"] == 0
        assert s["preference_rules"] == 0


# ─── 6. Schema Migration ────────────────────────────────────────────────────


class TestSchemaMigration:

    def test_source_column_exists(self, mem: LongTermMemory):
        """The 'source' column should exist in the facts table."""
        conn = mem._get_conn()
        # This should not raise
        conn.execute("SELECT source FROM facts LIMIT 1")

    def test_new_tables_exist(self, mem: LongTermMemory):
        """learned_workflows and preference_rules tables should exist."""
        conn = mem._get_conn()
        conn.execute("SELECT * FROM learned_workflows LIMIT 1")
        conn.execute("SELECT * FROM preference_rules LIMIT 1")
