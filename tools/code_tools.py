"""
ALEX — Code Tools
Sandboxed Python execution, script running, and output capture.
"""

import io
import sys
import subprocess
import textwrap
import tempfile
import os
from pathlib import Path

from core.tool_registry import tool, ToolResult, SafetyLevel
from utils.logger import log
import config


def _denied_pattern(command: str) -> str | None:
    """
    Return the deny-list entry this command matches, or None.

    These are commands confirmation should not be able to authorise — a
    mistyped approval shouldn't be able to wipe the disk. Normalised on
    whitespace so `del  /f /s /q  C:\\` matches too.
    """
    normalised = " ".join(command.lower().split())
    for pattern in config.SHELL_DENY_PATTERNS:
        if " ".join(pattern.lower().split()) in normalised:
            return pattern
    return None


@tool(
    name="code_run",
    description="Execute Python code and return stdout/stderr output. Use for calculations, data processing, and automation scripts.",
    parameters={
        "code": {"type": "string", "description": "Python code to execute", "required": True},
        "timeout": {"type": "integer", "description": "Execution timeout in seconds (default: 30)", "required": False},
    },
    category="code",
    safety=SafetyLevel.CONFIRM,
    examples=["code_run({'code': 'import math\\nprint(math.pi)', 'timeout': 10})"],
)
def code_run(params: dict) -> ToolResult:
    code = params.get("code", "")
    timeout = int(params.get("timeout", 30))

    if not code:
        return ToolResult(success=False, error="No code provided")

    log.warning(f"💻 Executing code (timeout={timeout}s):\n{code[:200]}")

    try:
        # Write code to a temp file and execute in subprocess (safer than exec())
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        os.unlink(tmp_path)

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            output = stdout or "(no output)"
            log.info(f"✅ Code executed successfully. Output: {output[:100]}")
            return ToolResult(
                success=True,
                message=f"Code output:\n{output}",
                data={"stdout": stdout, "stderr": stderr, "returncode": 0},
            )
        else:
            error_msg = stderr or stdout or "Unknown error"
            log.error(f"❌ Code failed (rc={result.returncode}): {error_msg[:200]}")
            return ToolResult(
                success=False,
                error=f"Code failed:\n{error_msg}",
                data={"stdout": stdout, "stderr": stderr, "returncode": result.returncode},
            )

    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error=f"Code execution timed out after {timeout} seconds")
    except Exception as e:
        return ToolResult(success=False, error=f"Execution error: {e}")


@tool(
    name="shell_run",
    description="Run a Windows shell/PowerShell command and return output",
    parameters={
        "command": {"type": "string", "description": "Shell command to execute", "required": True},
        "shell": {"type": "string", "description": "'cmd' or 'powershell' (default: powershell)", "required": False},
        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)", "required": False},
    },
    category="code",
    safety=SafetyLevel.CONFIRM,
)
def shell_run(params: dict) -> ToolResult:
    command = params.get("command", "")
    shell_type = params.get("shell", "powershell")
    timeout = int(params.get("timeout", 30))

    if not command:
        return ToolResult(success=False, error="No command provided")

    blocked = _denied_pattern(command)
    if blocked:
        log.error(f"⛔ Refused shell command matching deny-list ({blocked!r}): {command}")
        return ToolResult(
            success=False,
            message="I won't run that — it matches a command pattern that's blocked for safety.",
            error=f"Command matches SHELL_DENY_PATTERNS entry {blocked!r}",
        )

    log.warning(f"🖥️ Running shell command ({shell_type}): {command}")

    try:
        if shell_type == "powershell":
            full_cmd = ["powershell", "-Command", command]
        else:
            full_cmd = ["cmd", "/c", command]

        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        if result.returncode == 0:
            return ToolResult(
                success=True,
                message=f"Command output:\n{output}" if output else "Command completed successfully.",
                data={"stdout": output, "stderr": error, "returncode": 0},
            )
        else:
            return ToolResult(
                success=False,
                error=f"Command failed (rc={result.returncode}):\n{error or output}",
                data={"stdout": output, "stderr": error, "returncode": result.returncode},
            )

    except subprocess.TimeoutExpired:
        return ToolResult(success=False, error=f"Command timed out after {timeout}s")
    except Exception as e:
        return ToolResult(success=False, error=f"Shell error: {e}")


@tool(
    name="code_evaluate",
    description="Evaluate a simple Python expression and return the result (safe, no file I/O)",
    parameters={
        "expression": {"type": "string", "description": "Python expression to evaluate", "required": True},
    },
    category="code",
)
def code_evaluate(params: dict) -> ToolResult:
    expression = params.get("expression", "")
    if not expression:
        return ToolResult(success=False, error="No expression provided")

    # Restrict dangerous builtins
    safe_globals = {
        "__builtins__": {
            "abs": abs, "round": round, "min": min, "max": max,
            "sum": sum, "len": len, "range": range, "list": list,
            "dict": dict, "set": set, "tuple": tuple, "str": str,
            "int": int, "float": float, "bool": bool,
            "sorted": sorted, "enumerate": enumerate, "zip": zip,
            "print": print,
        }
    }

    # Allow math and datetime
    try:
        import math
        import datetime
        safe_globals["math"] = math
        safe_globals["datetime"] = datetime
    except ImportError:
        pass

    try:
        result = eval(expression, safe_globals)  # noqa: S307
        return ToolResult(success=True, message=f"{expression} = {result}", data={"result": result})
    except Exception as e:
        return ToolResult(success=False, error=f"Evaluation error: {e}")
