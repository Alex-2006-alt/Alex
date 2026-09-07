"""
ALEX — Personal AI Assistant
Centralized Configuration
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
RECORDINGS_DIR = DATA_DIR / "recordings"
MEMORY_DB_PATH = DATA_DIR / "memory.db"

# Create required directories
for _dir in [DATA_DIR, LOGS_DIR, RECORDINGS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ─── Assistant Identity ──────────────────────────────────────────────────────
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Alex")
WAKE_WORD = os.getenv("WAKE_WORD", "hey alex")

# ─── Audio Settings ──────────────────────────────────────────────────────────
SAMPLE_RATE = 16000          # Whisper expects 16kHz
CHANNELS = 1                 # Mono audio
RECORD_SECONDS_MAX = 30      # Max recording length per utterance
SILENCE_THRESHOLD = float(os.getenv("SILENCE_THRESHOLD", "0.003"))  # Amplitude below this = silence
SILENCE_DURATION = 1.5       # Seconds of silence to stop recording
AUDIO_BLOCK_SIZE = 1024      # Audio buffer block size

# Audio input device index (None = system default, or set to device number)
# Run the mic diagnostic to find the correct device index for your system
_audio_dev = os.getenv("AUDIO_INPUT_DEVICE", "")
AUDIO_INPUT_DEVICE: int | None = int(_audio_dev) if _audio_dev.strip() else None

# ─── Speech-to-Text (Whisper) ────────────────────────────────────────────────
# Model sizes: tiny, base, small, medium, large
# tiny  = ~1GB RAM, fastest, least accurate
# base  = ~1GB RAM, good balance (RECOMMENDED for start)
# small = ~2GB RAM, better accuracy
# medium = ~5GB RAM, very good
# large = ~10GB RAM, best accuracy but slow without GPU
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")  # None for auto-detect

# ─── Text-to-Speech ──────────────────────────────────────────────────────────
# Options: "pyttsx3" (basic, offline), "coqui" (neural, needs GPU)
TTS_ENGINE = os.getenv("TTS_ENGINE", "pyttsx3")
TTS_RATE = int(os.getenv("TTS_RATE", "175"))        # Words per minute
TTS_VOLUME = float(os.getenv("TTS_VOLUME", "0.9"))  # 0.0 to 1.0

# ─── AI Brain (LLM) ──────────────────────────────────────────────────────────
# Provider: "ollama" (local), "gemini" (Google), "openai" (OpenAI), "openrouter" (free/cheap models)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")

# ─── Agentic Mode ─────────────────────────────────────────────────────────────
# When True, complex multi-step requests use the Planner + ReAct loop
AGENT_MODE = os.getenv("AGENT_MODE", "true").lower() == "true"
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "10"))   # Max steps per plan
AGENT_TIMEOUT = int(os.getenv("AGENT_TIMEOUT", "120"))       # Seconds before timeout
# How many execute → reflect rounds a single goal may take. 1 disables the
# ReAct loop and runs the initial plan only.
MAX_AGENT_ITERATIONS = int(os.getenv("MAX_AGENT_ITERATIONS", "3"))
PARALLEL_STEPS = os.getenv("PARALLEL_STEPS", "true").lower() == "true"  # Parallel independent steps

# Ollama settings (local LLM)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")

# Google Gemini settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# OpenAI settings
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# OpenRouter settings (free tier available — openrouter.ai)
# Compatible with OpenAI SDK, supports 200+ models
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# LLM Parameters
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "2048"))
CONTEXT_WINDOW_SIZE = int(os.getenv("CONTEXT_WINDOW_SIZE", "20"))  # Messages to keep
LLM_RETRY_COUNT = int(os.getenv("LLM_RETRY_COUNT", "2"))           # Retries on empty/failed LLM response
LLM_RETRY_DELAY = float(os.getenv("LLM_RETRY_DELAY", "0.5"))       # Base delay between retries (seconds)

# ─── Wake Word Detection ─────────────────────────────────────────────────────
# "porcupine" (Picovoice, needs key) or "whisper" (use Whisper, higher CPU)
WAKE_WORD_ENGINE = os.getenv("WAKE_WORD_ENGINE", "whisper")
PORCUPINE_ACCESS_KEY = os.getenv("PORCUPINE_ACCESS_KEY", "")

# ─── PC Control Settings ─────────────────────────────────────────────────────
# Safety: require confirmation for these action types
DANGEROUS_ACTIONS = [
    "delete_file",
    "shutdown",
    "restart",
    "kill_process",
    "format_drive",
    "run_command",
]

# ─── Safety ───────────────────────────────────────────────────────────────────
# CONFIRM-level tools (shell_run, system_power, file_delete, process_kill,
# code_run) are denied unless the caller supplies a confirmation channel.
# Set this true to let multi-step plans run them unattended. Leave it false.
AGENT_AUTO_CONFIRM = os.getenv("AGENT_AUTO_CONFIRM", "false").lower() == "true"

# Seconds a pending web-UI confirmation stays valid before it expires
CONFIRMATION_TIMEOUT = int(os.getenv("CONFIRMATION_TIMEOUT", "120"))

# Substrings that are never allowed in a shell_run command, checked
# case-insensitively before execution. Confirmation is not enough for these.
SHELL_DENY_PATTERNS = [
    "format ",
    "diskpart",
    "reg delete",
    "vssadmin delete",
    "bcdedit",
    "cipher /w",
    "del /f /s /q c:\\",
    "rd /s /q c:\\",
    "remove-item -recurse -force c:\\",
    "mkfs",
    "rm -rf /",
]

# Enforce ALLOWED_FILE_PATHS on the tools that MODIFY the filesystem
# (file_write, file_move, file_copy, file_delete, file_mkdir). Reading and
# listing stay unrestricted. Set false to allow writes anywhere.
ENFORCE_FILE_ALLOWLIST = os.getenv("ENFORCE_FILE_ALLOWLIST", "true").lower() == "true"

# Directories Alex may modify. Empty list = no restriction (USE WITH CAUTION).
# Add your project roots here if you want Alex writing into them.
ALLOWED_FILE_PATHS = [
    str(Path.home()),          # User home directory
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
]

# App registry: common app names → paths (auto-discovered at runtime too)
DEFAULT_APP_REGISTRY = {
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "explorer": "explorer.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "vscode": "code",
    "word": "winword.exe",
    "excel": "excel.exe",
    "paint": "mspaint.exe",
    "snipping tool": "snippingtool.exe",
    "task manager": "taskmgr.exe",
    "control panel": "control.exe",
    "settings": "ms-settings:",
}

# ─── Integrations (used by tools/notification_tools.py) ───────────────────────
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_TO_FILE = os.getenv("LOG_TO_FILE", "true").lower() == "true"

# ─── System Prompt for LLM ───────────────────────────────────────────────────
#
# DEPRECATED — kept only as documentation of the response format. Brain builds
# its system prompt from live ToolRegistry descriptions (see
# Brain._build_system_prompt); the action names below no longer exist as tools
# and only resolve through ToolRegistry._find_by_alias.
_LEGACY_SYSTEM_PROMPT = f"""You are {ASSISTANT_NAME}, a helpful personal AI assistant running on the user's Windows PC.
You can control the PC, manage files, open apps, search the web, and more.

CRITICAL RULES:
1. When the user asks you to perform a PC action, respond with BOTH a friendly message AND a JSON action block.
2. The JSON action block MUST be on its own line, wrapped in ```action``` code fences.
3. If no PC action is needed (just conversation), respond normally without an action block.
4. Always be concise, helpful, and friendly.
5. For dangerous actions (deleting files, shutting down), warn the user first.

AVAILABLE ACTIONS (use these exact action names):
- open_app: Open an application. Params: {{"name": "app_name"}}
- close_app: Close an application. Params: {{"name": "app_name"}}
- search_web: Search the web. Params: {{"query": "search terms"}}
- open_url: Open a URL. Params: {{"url": "https://..."}}
- take_screenshot: Take a screenshot. Params: {{"region": "full"}} or {{"region": "select"}}
- type_text: Type text. Params: {{"text": "text to type"}}
- press_key: Press a key combo. Params: {{"keys": "ctrl+c"}}
- volume_control: Control volume. Params: {{"action": "up|down|mute", "amount": 10}}
- file_operation: File ops. Params: {{"operation": "move|copy|delete|search|create_folder", "source": "path", "destination": "path"}}
- run_command: Run a shell command. Params: {{"command": "command string"}}
- system_control: System ops. Params: {{"action": "shutdown|restart|sleep|lock"}}
- kill_process: Kill a process. Params: {{"name": "process_name"}}
- set_reminder: Set a reminder. Params: {{"message": "reminder text", "minutes": 30}}
- get_weather: Get weather. Params: {{"city": "city_name"}}
- media_control: Control media. Params: {{"action": "play|pause|next|previous"}}
- clipboard: Clipboard ops. Params: {{"action": "copy|paste", "text": "optional text"}}
- send_email: Send an email. Params: {{"to": "recipient@email.com", "subject": "Subject", "body": "Email body text"}}
- run_code: Execute code. Params: {{"code": "print('hello')", "language": "python|javascript|shell"}}

RESPONSE FORMAT EXAMPLE:
User: "Open Chrome"
Response: Sure, opening Chrome for you!
```action
{{"action": "open_app", "params": {{"name": "chrome"}}}}
```

User: "What's the weather?"
Response: Let me check the weather for you!
```action
{{"action": "get_weather", "params": {{"city": "auto"}}}}
```

User: "Send an email to john@example.com saying hello"
Response: Sending that email now!
```action
{{"action": "send_email", "params": {{"to": "john@example.com", "subject": "Hello", "body": "Hello John!"}}}}
```

User: "Run this Python code: print(2+2)"
Response: Running that code for you!
```action
{{"action": "run_code", "params": {{"code": "print(2+2)", "language": "python"}}}}
```

User: "How are you?"
Response: I'm doing great! Ready to help you with anything. What do you need?
"""
