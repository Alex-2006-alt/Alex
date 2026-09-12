"""
ALEX — Explicit Memory Tools
Tools that allow the LLM to explicitly read and write to the persistent SQLite memory.
"""

from core.tool_registry import tool, SafetyLevel
from memory.long_term import LongTermMemory
from utils.logger import log

@tool(
    name="memory_store",
    description="Explicitly save an important fact about the user (e.g., name, preference, background) to long-term memory so you don't forget it.",
    parameters={
        "key": {"type": "str", "description": "A short, unique identifier for the fact (e.g., 'user_favorite_drink', 'user_location', 'partner_name')", "required": True},
        "value": {"type": "str", "description": "The fact to remember (e.g., 'Coffee', 'New York', 'Sarah')", "required": True}
    },
    safety=SafetyLevel.SAFE,
    examples=[
        "user: my wife's name is Sarah -> memory_store {'key': 'wife_name', 'value': 'Sarah'}",
        "user: remember that i prefer dark mode -> memory_store {'key': 'ui_preference', 'value': 'Dark Mode'}"
    ]
)
def memory_store(params: dict) -> str:
    """Store a fact in the long-term memory."""
    key = params.get("key")
    value = params.get("value")
    
    if not key or not value:
        return "Error: Missing 'key' or 'value'."

    # Basic normalization of key format
    key = key.lower().replace(" ", "_")

    mem = LongTermMemory()
    mem.remember(key, value, category="explicit_fact")
    return f"Successfully remembered: {key} = {value}"

@tool(
    name="memory_forget",
    description="Delete a previously stored fact from long-term memory.",
    parameters={
        "key": {"type": "str", "description": "The exact key of the fact to forget (e.g., 'user_location')", "required": True}
    },
    safety=SafetyLevel.SAFE,
    examples=[
        "user: i don't live in New York anymore -> memory_forget {'key': 'user_location'}"
    ]
)
def memory_forget(params: dict) -> str:
    """Delete a fact from long-term memory."""
    key = params.get("key")
    
    if not key:
        return "Error: Missing 'key'."

    key = key.lower().replace(" ", "_")

    mem = LongTermMemory()
    deleted = mem.forget(key)
    
    if deleted:
        return f"Successfully forgot the fact associated with '{key}'."
    else:
        return f"No fact found with the key '{key}' to forget."
