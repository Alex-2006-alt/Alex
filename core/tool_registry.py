"""
ALEX — Tool Registry
Dynamic, self-describing tool system that replaces hardcoded action handlers.
Tools declare their own name, description, parameters, and safety level.
The LLM reads live tool descriptions instead of a hardcoded system prompt list.
"""

import inspect
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from utils.logger import log


class SafetyLevel(Enum):
    SAFE = "safe"           # No confirmation needed
    WARN = "warn"           # Log warning, proceed
    CONFIRM = "confirm"     # Require user confirmation


@dataclass
class ToolResult:
    """Standardized result from any tool execution."""
    success: bool
    data: Any = None                     # Structured data (list, dict, etc.)
    message: str = ""                    # Human-readable result
    artifacts: list[str] = field(default_factory=list)   # File paths created
    error: str | None = None

    def to_response(self) -> str:
        """Convert to a string suitable for the LLM or TTS."""
        if not self.success:
            return f"Error: {self.error or 'Unknown error'}"
        return self.message or str(self.data)[:500]

    def __str__(self):
        return self.to_response()


@dataclass
class ToolSpec:
    """Metadata describing a registered tool."""
    name: str
    description: str
    fn: Callable
    parameters: dict          # {param_name: {"type": str, "description": str, "required": bool}}
    safety: SafetyLevel = SafetyLevel.SAFE
    category: str = "general"
    examples: list[str] = field(default_factory=list)
    #: Optional ``fn(params) -> ToolResult | None`` run BEFORE the confirmation
    #: gate. Return a ToolResult to reject the call outright — used for inputs
    #: no approval should be able to authorise, so the user is never asked to
    #: approve something that will be refused anyway.
    precheck: Callable | None = None
    #: Optional ``fn(params) -> str`` to produce a human sentence for confirmation
    confirm_summary: Callable | None = None

    def prompt_description(self) -> str:
        """Format tool for inclusion in an LLM prompt."""
        param_lines = []
        for pname, pmeta in self.parameters.items():
            req = "required" if pmeta.get("required", False) else "optional"
            param_lines.append(f"    - {pname} ({pmeta.get('type', 'str')}, {req}): {pmeta.get('description', '')}")

        params_str = "\n".join(param_lines) if param_lines else "    (no parameters)"
        safety_note = f" ⚠️ REQUIRES CONFIRMATION" if self.safety == SafetyLevel.CONFIRM else ""

        return (
            f"- **{self.name}**{safety_note}: {self.description}\n"
            f"  Category: {self.category}\n"
            f"  Parameters:\n{params_str}"
        )


def _auto_approve(_name: str, _params: dict) -> bool:
    """Explicit opt-in for unattended execution of CONFIRM-level tools."""
    return True


class ToolRegistry:
    """
    Central registry for all Alex tools.
    Tools register themselves via the @tool decorator.
    """
    _instance: "ToolRegistry | None" = None

    #: Pass as ``confirm_callback`` to run CONFIRM-level tools without asking.
    #: Deliberately verbose at the call site — this is the dangerous option.
    AUTO_APPROVE = staticmethod(_auto_approve)

    def __init__(self):
        self._tools: dict[str, ToolSpec] = {}

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register(self, spec: ToolSpec):
        """Register a tool specification."""
        self._tools[spec.name] = spec
        log.debug(f"🔧 Tool registered: {spec.name} [{spec.category}]")

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def execute(self, name: str, params: dict, confirm_callback: Callable | None = None) -> ToolResult:
        """
        Execute a tool by name with given parameters.

        Args:
            name: Tool name
            params: Parameters dict
            confirm_callback: Called for CONFIRM-level tools; returns bool.
                A CONFIRM-level tool is **denied** when this is None — a caller
                with no way to ask the user has no way to approve either.
                Callers that genuinely want unattended execution must opt in
                explicitly by passing ``ToolRegistry.AUTO_APPROVE``.
        """
        spec = self._tools.get(name)
        if not spec:
            # Try legacy compatibility (action names from config.py system prompt)
            spec = self._find_by_alias(name)

        if not spec:
            available = ", ".join(sorted(self._tools.keys()))
            return ToolResult(
                success=False,
                error=f"Unknown tool '{name}'. Available: {available}"
            )

        # Hard rejections come first: no point asking the user to approve
        # something that is refused regardless of the answer.
        if spec.precheck:
            objection = spec.precheck(params)
            if objection is not None:
                return objection

        # Safety check — deny by default when there is no confirmation channel
        if spec.safety == SafetyLevel.CONFIRM:
            if confirm_callback is None:
                log.warning(f"🚫 Blocked '{name}': requires confirmation, no confirmation channel available")
                return ToolResult(
                    success=False,
                    message=f"'{name}' needs your confirmation, and I had no way to ask.",
                    error="Confirmation required but no confirm_callback was provided",
                )
            if not confirm_callback(name, params):
                return ToolResult(
                    success=False,
                    message=f"Action '{name}' was cancelled by user.",
                    error="User denied confirmation"
                )

        # Execute
        try:
            log.info(f"⚡ Executing tool: {name} | params: {params}")
            result = spec.fn(params)

            # Normalize result
            if isinstance(result, ToolResult):
                return result
            if isinstance(result, str):
                return ToolResult(success=True, message=result, data=result)
            if isinstance(result, dict):
                return ToolResult(success=True, data=result, message=str(result)[:300])
            return ToolResult(success=True, data=result, message=str(result)[:300])

        except Exception as e:
            log.error(f"Tool '{name}' failed: {e}\n{traceback.format_exc()}")
            return ToolResult(success=False, error=str(e))

    def _find_by_alias(self, name: str) -> ToolSpec | None:
        """Find a tool by alternate names/aliases for backward compatibility."""
        aliases = {
            "open_app": "app_open",
            "close_app": "app_close",
            "search_web": "web_search",
            "open_url": "web_open",
            "file_operation": "file_op",
            "volume_control": "system_volume",
            "system_control": "system_power",
            "kill_process": "process_kill",
            "take_screenshot": "screenshot_capture",
            "type_text": "keyboard_type",
            "press_key": "keyboard_press",
            "media_control": "media_play",
            "set_reminder": "reminder_set",
            "get_weather": "weather_get",
            "run_code": "code_run",
            "run_command": "shell_run",
            "send_email": "email_send",
        }
        canonical = aliases.get(name, name)
        return self._tools.get(canonical)

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def list_by_category(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for name, spec in self._tools.items():
            result.setdefault(spec.category, []).append(name)
        return result

    def get_descriptions_for_prompt(self) -> str:
        """
        Return all tool descriptions formatted for the LLM system prompt.
        Groups by category for readability.
        """
        by_cat = self.list_by_category()
        lines = []
        for category in sorted(by_cat.keys()):
            lines.append(f"\n### {category.upper()} TOOLS")
            for tool_name in sorted(by_cat[category]):
                spec = self._tools[tool_name]
                lines.append(spec.prompt_description())
        return "\n".join(lines)

    def get_json_schema(self) -> dict:
        """Return OpenAI-compatible function calling schema for all tools."""
        functions = []
        for name, spec in self._tools.items():
            props = {}
            required = []
            for pname, pmeta in spec.parameters.items():
                props[pname] = {
                    "type": pmeta.get("type", "string"),
                    "description": pmeta.get("description", ""),
                }
                if pmeta.get("required", False):
                    required.append(pname)

            functions.append({
                "name": name,
                "description": spec.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            })
        return functions

    def __len__(self):
        return len(self._tools)


# ─── @tool Decorator ─────────────────────────────────────────────────────────

def tool(
    name: str,
    description: str,
    parameters: dict | None = None,
    safety: SafetyLevel = SafetyLevel.SAFE,
    category: str = "general",
    examples: list[str] | None = None,
    precheck: Callable | None = None,
    confirm_summary: Callable | None = None,
):
    """
    Decorator to register a function as an Alex tool.

    Usage:
        @tool(
            name="web_search",
            description="Search the web for information",
            parameters={
                "query": {"type": "string", "description": "Search terms", "required": True},
                "num_results": {"type": "integer", "description": "Number of results", "required": False},
            },
            category="web",
        )
        def web_search(params: dict) -> ToolResult:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        spec = ToolSpec(
            name=name,
            description=description,
            fn=fn,
            parameters=parameters or {},
            safety=safety,
            category=category,
            examples=examples or [],
            precheck=precheck,
            confirm_summary=confirm_summary,
        )
        ToolRegistry.get_instance().register(spec)
        return fn

    return decorator


