# A.L.E.X — Advanced Linguistic Executive System

> Your personal AI assistant that listens, talks, controls your PC, and does work for you.

---

## 🚀 Quick Start

### 1. Install dependencies
```bash
cd e:\alex
pip install -r requirements.txt
```

### 2. Add your Gemini API key
Edit `.env` and set:
```
GEMINI_API_KEY=your_key_here
```
Get a free key: https://aistudio.google.com/apikey

### 3. Run ALEX

```bash
# 🌐 JARVIS Web Interface (recommended — opens in browser)
python main.py --server

# ⌨️ Text-only mode (type commands in terminal)
python main.py --text

# 🎤 Voice mode with wake word ("Hey Alex")
python main.py

# 🎤 Voice mode, always listening (no wake word)
python main.py --no-wake-word

# 🧪 Run diagnostic tests
python main.py --test
```

---

## ✨ Features

### 🧠 AI Brain
- **Multi-provider LLM**: Gemini (cloud), OpenAI (cloud), Ollama (local)
- **Conversational memory**: Session-based + persistent SQLite storage
- **Context awareness**: Active window, time of day, recent actions
- **Structured action protocol**: LLM returns JSON action blocks for PC control

### 🎤 Voice
- **Whisper STT**: Transcribe speech using OpenAI Whisper (local, no API needed)
- **pyttsx3 TTS**: Offline text-to-speech
- **Wake word detection**: "Hey Alex" using Whisper tiny model

### 💻 PC Control (9 action modules)
| Module | Capabilities |
|--------|-------------|
| App Launcher | Open/close apps, auto-discover from Start Menu & PATH |
| System Control | Volume, shutdown, restart, sleep, lock screen |
| File Manager | Search, move, copy, delete, list, disk usage |
| Web Browser | Open URLs, search Google/YouTube/Bing |
| Keyboard & Mouse | Type text, press hotkeys (Ctrl+C, Alt+Tab, etc.) |
| Screenshot | Full screen capture, auto-save to Desktop |
| Media Control | Play/pause, next/previous track |
| Process Manager | List top processes, kill by name |
| Clipboard | Copy, paste, read clipboard content |

### 🔌 Plugins (4 active)
| Plugin | What It Does |
|--------|-------------|
| Weather | Current conditions from OpenWeatherMap |
| Reminders | Background timers with voice alerts |
| Email | Send emails via Gmail/Outlook SMTP |
| Code Runner | Execute Python, JavaScript, PowerShell snippets |

### 🌐 JARVIS Web Interface
- Holographic dark-mode HUD inspired by Iron Man
- Real-time system stats (CPU, RAM, Disk, Battery, Network)
- Animated AI core with rotating rings and state-based effects
- Chat interface connected to the Python backend via REST API
- Audio waveform visualizer
- Works standalone in demo mode, or with full backend power

---

## 📁 Project Structure

```
e:\alex\
├── main.py                  # Entry point (voice, text, server, test)
├── server.py                # Flask web API server
├── config.py                # All settings + LLM system prompt
├── requirements.txt         # Python dependencies
├── .env                     # API keys (fill in your own)
├── README.md                # This file
│
├── core/                    # Engine
│   ├── listener.py          # Whisper STT
│   ├── speaker.py           # pyttsx3 TTS
│   ├── wake_word.py         # "Hey Alex" detection
│   ├── brain.py             # LLM integration
│   ├── action_router.py     # Routes actions + plugin auto-discovery
│   └── assistant.py         # Main orchestrator
│
├── actions/                 # PC Control modules
│   ├── app_launcher.py
│   ├── system_control.py
│   ├── file_manager.py
│   ├── web_browser.py
│   ├── keyboard_mouse.py
│   ├── screenshot.py
│   ├── media_control.py
│   ├── process_manager.py
│   └── clipboard_manager.py
│
├── plugins/                 # Extensible plugin system
│   ├── plugin_loader.py     # Auto-discovers *_plugin.py files
│   ├── weather_plugin.py
│   ├── reminder_plugin.py
│   ├── email_plugin.py
│   └── code_runner_plugin.py
│
├── memory/                  # Persistence & context
│   ├── storage.py           # SQLite DB
│   ├── conversation.py      # Chat history
│   └── context.py           # Active window, time, etc.
│
├── utils/                   # Utilities
│   ├── logger.py
│   ├── audio_utils.py
│   └── system_info.py
│
└── gui/                     # JARVIS Web Interface
    ├── index.html           # Main page
    ├── style.css            # Holographic theme
    └── app.js               # Frontend logic + API client
```

---

## ⚙️ Configuration

All settings are in `.env`. Key options:

| Setting | Default | Description |
|---------|---------|-------------|
| `GEMINI_API_KEY` | *(empty)* | Your Google Gemini API key |
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai`, or `ollama` |
| `WHISPER_MODEL_SIZE` | `base` | `tiny`, `base`, `small`, `medium`, `large` |
| `WAKE_WORD` | `hey alex` | Custom wake word |
| `EMAIL_ADDRESS` | *(empty)* | Gmail/Outlook for email plugin |
| `EMAIL_PASSWORD` | *(empty)* | App Password (not regular password) |
| `OPENWEATHER_API_KEY` | *(empty)* | For weather plugin |

---

## 🎨 JARVIS Interface Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Enter` | Send message |
| `Ctrl+L` | Focus chat input |
| `Ctrl+M` | Toggle microphone |
| `Escape` | Return to standby |

---

## 🔧 Adding Custom Plugins

Create a file in `plugins/` named `*_plugin.py`:

```python
from plugins.plugin_loader import PluginBase

class MyPlugin(PluginBase):
    name = "my_plugin"
    description = "What it does"
    actions = ["my_action"]

    def execute(self, params: dict) -> str:
        # Your logic here
        return "Result message"
```

It auto-registers on startup. The LLM can invoke it via `{"action": "my_action", "params": {...}}`.

---

## 📜 License

Personal project. Built with ❤️ as your own JARVIS.
