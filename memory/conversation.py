"""
ALEX — Conversation Memory
Manages chat history with sliding window and context for the AI brain.
"""

from datetime import datetime

from utils.logger import log
from memory.storage import Storage
import config


class ConversationMemory:
    """
    Manages conversation history with a sliding context window.
    Stores messages persistently and provides context for the LLM.
    """

    def __init__(self, storage: Storage | None = None):
        self.storage = storage or Storage()
        self.session_messages: list[dict] = []
        self.max_context = config.CONTEXT_WINDOW_SIZE
        log.info("💬 Conversation memory initialized")

    def add_message(self, role: str, content: str, action: str = None, params: dict = None):
        """
        Add a message to conversation history.

        Args:
            role: 'user' or 'assistant'
            content: Message content
            action: Action that was taken (if any)
            params: Action parameters (if any)
        """
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "params": params,
        }

        self.session_messages.append(message)

        # Persist to SQLite
        self.storage.save_message(role, content, action, params)

        # Trim session messages to context window
        if len(self.session_messages) > self.max_context * 2:
            self.session_messages = self.session_messages[-(self.max_context * 2):]

    def get_context_messages(self) -> list[dict]:
        """
        Get messages formatted for LLM context.

        Returns:
            List of {role, content} dicts for the LLM
        """
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in self.session_messages[-(self.max_context * 2):]
        ]

    def search(self, query: str) -> list[dict]:
        """Search conversation history."""
        return self.storage.search_conversations(query)

    def get_summary(self) -> str:
        """Get a summary of the current session."""
        if not self.session_messages:
            return "No conversation yet."

        user_messages = [m for m in self.session_messages if m["role"] == "user"]
        return (
            f"This session has {len(self.session_messages)} messages "
            f"({len(user_messages)} from you). "
            f"Started at {self.session_messages[0]['timestamp'][:16]}."
        )

    def clear_session(self):
        """Clear current session messages (persistent history is kept)."""
        self.session_messages.clear()
        log.info("Session memory cleared")
