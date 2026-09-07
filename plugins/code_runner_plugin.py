"""
ALEX — Code Runner Plugin
Execute Python, JavaScript (Node.js), and shell code snippets safely.
Runs code in a subprocess with timeout protection.
"""

import subprocess
import tempfile
import os
from pathlib import Path

from plugins.plugin_loader import PluginBase
from utils.logger import log
import config


class CodeRunnerPlugin(PluginBase):
    """Run code snippets in various languages."""

    name = "code_runner"
    description = "Execute Python, JavaScript, or shell code snippets"
    actions = ["run_code"]

    # Maximum execution time in seconds
    TIMEOUT = 30

    # Maximum output length (characters)
    MAX_OUTPUT = 5000

    # Dangerous patterns to block (basic sandboxing)
    BLOCKED_PATTERNS = [
        "os.remove", "os.unlink", "shutil.rmtree",
        "format(", "os.system(\"rm", "os.system(\"del",
        "__import__('os').system",
        "subprocess.call(['rm",
        "import ctypes",
    ]

    def execute(self, params: dict) -> str:
        """
        Run a code snippet.

        Params:
            code: The code to execute
            language: 'python', 'javascript', 'shell' (default: 'python')
        """
        code = params.get("code", "")
        language = params.get("language", "python").lower()

        if not code:
            return "No code provided. Please specify the code to run."

        # Basic safety check
        safety_check = self._safety_check(code, language)
        if safety_check:
            return safety_check

        if language in ("python", "py"):
            return self._run_python(code)
        elif language in ("javascript", "js", "node"):
            return self._run_javascript(code)
        elif language in ("shell", "cmd", "powershell", "ps1"):
            return self._run_shell(code)
        else:
            return f"Unsupported language: '{language}'. Supported: python, javascript, shell."

    def _safety_check(self, code: str, language: str) -> str | None:
        """
        Basic safety check for dangerous patterns.
        Returns error message if blocked, None if safe.
        """
        code_lower = code.lower()

        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in code_lower:
                log.warning(f"🚫 Code runner blocked dangerous pattern: {pattern}")
                return (
                    f"⚠️ Code contains a potentially dangerous pattern: '{pattern}'. "
                    f"For safety, this has been blocked. If you need to perform file operations, "
                    f"use the file_operation action instead."
                )

        return None

    def _run_python(self, code: str) -> str:
        """Run Python code in a subprocess."""
        log.info(f"🐍 Running Python code ({len(code)} chars)")

        # Write code to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=config.DATA_DIR, prefix="alex_code_"
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = subprocess.run(
                ["python", temp_path],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                cwd=str(Path.home()),
            )
            return self._format_output(result, "Python")

        except subprocess.TimeoutExpired:
            return f"⏱️ Python code timed out after {self.TIMEOUT} seconds."
        except FileNotFoundError:
            return "Python interpreter not found. Make sure Python is installed and on PATH."
        except Exception as e:
            return f"Error running Python code: {e}"
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _run_javascript(self, code: str) -> str:
        """Run JavaScript code using Node.js."""
        log.info(f"📜 Running JavaScript code ({len(code)} chars)")

        # Write code to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, dir=config.DATA_DIR, prefix="alex_code_"
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = subprocess.run(
                ["node", temp_path],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                cwd=str(Path.home()),
            )
            return self._format_output(result, "JavaScript")

        except subprocess.TimeoutExpired:
            return f"⏱️ JavaScript code timed out after {self.TIMEOUT} seconds."
        except FileNotFoundError:
            return "Node.js not found. Install Node.js from https://nodejs.org/ to run JavaScript."
        except Exception as e:
            return f"Error running JavaScript code: {e}"
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def _run_shell(self, code: str) -> str:
        """Run a shell/PowerShell command."""
        log.info(f"💻 Running shell command ({len(code)} chars)")

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", code],
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT,
                cwd=str(Path.home()),
            )
            return self._format_output(result, "Shell")

        except subprocess.TimeoutExpired:
            return f"⏱️ Shell command timed out after {self.TIMEOUT} seconds."
        except Exception as e:
            return f"Error running shell command: {e}"

    def _format_output(self, result: subprocess.CompletedProcess, language: str) -> str:
        """Format the subprocess output into a readable message."""
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        # Truncate long outputs
        if len(stdout) > self.MAX_OUTPUT:
            stdout = stdout[:self.MAX_OUTPUT] + "\n... (output truncated)"
        if len(stderr) > self.MAX_OUTPUT:
            stderr = stderr[:self.MAX_OUTPUT] + "\n... (output truncated)"

        if result.returncode == 0:
            if stdout:
                return f"✅ {language} executed successfully:\n{stdout}"
            return f"✅ {language} code ran successfully with no output."
        else:
            parts = [f"❌ {language} exited with code {result.returncode}."]
            if stderr:
                parts.append(f"Error:\n{stderr}")
            elif stdout:
                parts.append(f"Output:\n{stdout}")
            return "\n".join(parts)
