# A.L.E.X — Feature Plan: YouTube, Power, Startup Greeting, WhatsApp, Phone

Requested: play/search YouTube, switch off the PC, greet me when I turn the PC
on, send WhatsApp messages, make calls on my phone.

Before any of that: **two of these already work, and the reason they look
broken is something else.** Part 0 covers what the logs actually show. Fixing
it comes first, because every new feature below is invoked through the same
LLM and the same browser, and will appear just as broken until it's fixed.

---

## Part 0 — Why it looks broken today

Read from `data/logs/alex_2026-09-07.log`, your session at 18:36–18:40.

### 0.1 The LLM fails about half the time — this is the big one

```
18:37:20  LLM call with history failed (attempt 1): Error code: 404 -
          {'error': {'message': 'Provider returned error', 'code': 404,
           'provider_name': 'Nvidia'}}
18:37:21  LLM call with history failed (attempt 2): (same)
18:37:23  LLM call with history failed (attempt 3): 'NoneType' object is not subscriptable
18:37:23  Response: "Sorry, I had trouble with that."
```

`OPENROUTER_MODEL=nvidia/nemotron-3-super-120b-a12b:free`. The model id is
valid — I checked it against OpenRouter's catalogue — but the free Nvidia
provider behind it returns 404 under load. Roughly half your requests died this
way. When Alex "can't do anything", most of the time it never got a reply from
the model at all.

There is a second bug stacked on top. When OpenRouter returns an error body,
there is no `choices` array, and `response.choices[0].message.content`
(`core/brain.py:557`) raises `'NoneType' object is not subscriptable` — an
unhandled crash instead of a clean retry.

Your `.env` has **only** an OpenRouter key. No Gemini, no OpenAI.

### 0.2 YouTube already works — you just can't see the tab

```
18:37:28  Fast path: action=web_open
18:37:28  Executing tool: web_open | params: {'url': 'https://www.youtube.com/results?search_query=Chulo+song'}
18:37:28  Opened URL: https://www.youtube.com/results?search_query=Chulo+song
```

The tool ran and succeeded. Your next message was *"who are you open I can't
see anything"* — which is the actual bug. `webbrowser.open()` opens a new tab
**behind** the window you're looking at. You're in the ALEX interface; the
YouTube tab opens and never comes forward. Nothing raises the browser window.

It also only ever opens a *search results page*, so even when you see it, you
still have to click a video yourself. That's the feature gap.

### 0.3 Shutdown was never actually attempted

Every `system_power` line in today's log is from my test suite, not from you.
The tool exists and works. What will bite you when you try it: it's a
`CONFIRM`-level tool, so it now shows an approve/deny card in the web UI — and
if your browser has `app.js` cached from before today, that card never renders,
the request waits 120 seconds, and times out as a denial. Cache-busting is a
one-line fix, included below.

### 0.4 WhatsApp and phone calls genuinely don't exist

No tools for either. Part 5 and Part 6.

---

## Part 1 — Fix the foundation (do this first)

### 1.1 Make the LLM reliable

**Files:** `core/brain.py`, `config.py`, `.env.example`

1. **Validate the response shape.** Wrap the OpenAI-compatible response
   handling (`openai` and `openrouter` branches, both the `_single` methods) so
   a body without `choices` raises a clean `LLMError` the retry loop can catch,
   instead of a `TypeError` that escapes as "NoneType object is not
   subscriptable".

2. **Add a model fallback chain.** New setting:
   ```
   OPENROUTER_FALLBACK_MODELS=minimax/minimax-m3:free,google/gemma-4-31b-it:free
   ```
   On a 404/429/503 from the primary model, retry the *next model* rather than
   hammering the one that's down. There are 18 `:free` models available right
   now; a chain of three makes a dead provider a non-event.

3. **Add provider fallback.** If `LLM_PROVIDER` fails every retry and another
   provider has a key configured, fall through to it. Log the switch loudly.

4. **Get a Gemini key — this is the single highest-value thing you can do.**
   It's free at https://aistudio.google.com/apikey, and `gemini-2.0-flash` is
   far more reliable than the free OpenRouter pool. Set:
   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=...
   ```
   Keep OpenRouter configured as the fallback.

5. **Surface failures honestly in the UI.** Right now a dead model produces
   "Sorry, I had trouble with that. ('NoneType'...)" which tells you nothing.
   Map it to "My AI provider isn't responding — check your key or try again."

**Verification:** a test that feeds the OpenRouter error body through the parser
and asserts a clean retry, plus one asserting the fallback chain advances.

**Effort:** half a day. **Do this before anything else.**

### 1.2 Bring the browser to the front

**Files:** new `utils/window_utils.py`, `tools/web_tools.py`

`pygetwindow` 0.0.9 and `pyautogui` are already installed, so this needs no new
dependencies.

```python
# utils/window_utils.py
def focus_window(title_substring: str, timeout: float = 5.0) -> bool:
    """Wait for a window whose title contains the substring, then raise it."""
```

Poll `pygetwindow.getAllWindows()` until a title matches, then `.activate()`,
with a ctypes `SetForegroundWindow` fallback (pygetwindow's activate is flaky
when the calling process doesn't own the foreground).

Then `web_open` gains `focus: bool = True` and calls it after
`webbrowser.open()`. This alone fixes "I can't see anything".

**Effort:** 2 hours, and it unblocks YouTube, WhatsApp and playback control,
all of which need a focused window to send keystrokes to.

---

## Part 2 — YouTube: search, play, and control

**Files:** new `tools/youtube_tools.py`, register in `tools/__init__.py`

I tested the approach against live YouTube — searching `Chulo song` returns
video id `sFMRqxCexDk`, *"The Local Train — Choo Lo"*, which is the song you
were asking for. No API key needed.

### Three new tools

| Tool | Does | Safety |
|---|---|---|
| `youtube_search` | Returns the top N titles + video ids for a query, so Alex can say them aloud and you pick | SAFE |
| `youtube_play` | Resolves a query to the **first video** and opens it playing, focused and optionally fullscreen | SAFE |
| `youtube_control` | play/pause, next, previous, mute, fullscreen, seek, volume on whatever is playing | SAFE |

### How `youtube_play` resolves a query

1. If given a URL or an 11-character video id, use it directly.
2. Otherwise fetch `https://www.youtube.com/results?search_query=<q>` with a
   desktop User-Agent and pull the first `"videoId":"<11 chars>"` out of the
   embedded JSON, alongside the matching `"title":{"runs":[{"text":"..."}]}`.
3. Open `https://www.youtube.com/watch?v=<id>`, focus the window.
4. Optionally send `k` (play/pause) only if the page didn't autoplay, and `f`
   for fullscreen if `fullscreen: true`.

**Fallback:** if the scrape returns nothing — YouTube changes their payload
occasionally — fall back to today's behaviour (open the results page) and say
so, rather than failing. Add an optional `YOUTUBE_API_KEY` path using the
official Data API v3 for people who want it rock-solid.

### How `youtube_control` works

Focus the browser window, then send YouTube's own keyboard shortcuts with
pyautogui:

| Action | Key |
|---|---|
| play / pause | `k` |
| next video | `shift+n` |
| previous | `shift+p` |
| mute | `m` |
| fullscreen | `f` |
| forward / back 10s | `l` / `j` |
| volume up / down | `up` / `down` |
| captions | `c` |

Guard it: if no browser window matching `YouTube` is found, return a clear
"nothing is playing" rather than firing keystrokes into whatever *is* focused.
That guard matters — stray `k` presses into another app would be bad.

### Making the LLM choose these tools

Two supporting changes, or Alex will keep reaching for `web_open`:

- Give each tool `examples=[...]` in the `@tool` decorator — the registry
  already feeds these into the prompt.
- Add aliases in `ToolRegistry._find_by_alias`: `play_youtube`, `play_song`,
  `play_music` → `youtube_play`.

**Tests:** id extraction against a saved HTML fixture (no network in tests),
URL/id/query input handling, and the "no window found" guard.

**Effort:** 1 day.

---

## Part 3 — Switching the PC off

`system_power` already does this. The work is making it usable and safe.

**Files:** `tools/system_tools.py`, `gui/index.html`, `core/assistant.py`, `config.py`

1. **Cache-bust the GUI** so the approval card actually renders:
   `<script src="app.js?v=2">`, same for `style.css`. Without this your browser
   may still be running the pre-approval-card JavaScript.

2. **Default to a grace period.** New `SHUTDOWN_GRACE_SECONDS=30`. Alex says
   "Shutting down in 30 seconds — say *cancel shutdown* to stop me." Right now
   `delay_seconds` defaults to 0 and it goes instantly, with no way back.

3. **Make cancel discoverable.** "cancel shutdown" is already a built-in
   command (`Assistant._handle_special_commands`) that runs `shutdown /a`.
   Surface it in the confirmation card text and in the spoken warning.

4. **Confirm with the target named.** The card should read
   "Shut down this PC in 30 seconds?", not `system_power {'action': 'shutdown'}`.
   Add a `confirm_summary` to `ToolSpec` — an optional
   `fn(params) -> str` producing a human sentence for the card and the voice
   prompt. Every dangerous tool benefits, not just this one.

5. **Sleep is broken-ish on modern Windows.** `SetSuspendState 0,1,0`
   hibernates instead of sleeping when hibernation is enabled. Use
   `powercfg /hibernate off` detection or document it.

**Tests:** each action builds the right command (mock `os.system`), unknown
action rejected, grace period respected.

**Effort:** half a day.

---

## Part 4 — "Hello boss" when you turn the PC on

**Files:** new `scripts/install_startup.py`, `main.py`, `config.py`

### The greeting mode

Add `python main.py --greet`: loads **only** the Speaker (not Whisper, not the
LLM, not the tool registry — those take ~20 s and you want the greeting inside
5), speaks a line, exits.

```
Good morning, boss. It's Monday the 7th, 9:14 AM. Battery's at 46%.
```

Built from `memory/context.py` (time of day, username), `utils/system_info.py`
(battery, uptime), and new config:

```
GREETING_ENABLED=true
USER_TITLE=boss
GREETING_INCLUDE_STATUS=true
GREETING_DELAY_SECONDS=8
```

`GREETING_DELAY_SECONDS` matters: at logon the audio device often isn't ready
for several seconds, and pyttsx3 will silently say nothing. Wait, then speak,
and retry once if the TTS engine fails to initialise.

Optionally richer later: unread mail count, calendar, weather — but those need
the LLM up, so keep them out of the fast path.

### Making Windows run it

`scripts/install_startup.py` creates a shortcut in
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup` pointing at:

```
pythonw.exe E:\alex\main.py --greet
```

`pythonw.exe` (not `python.exe`) so no console window flashes up. The Startup
folder is user-writable — **no admin rights needed**, unlike a scheduled task.

Give it `--uninstall` to remove the shortcut, and `--with-server` to launch the
full assistant at logon instead of just greeting.

**Verification:** run `python main.py --greet` by hand, then
`python scripts/install_startup.py`, then reboot. If it's silent, check
`data/logs` — the greet mode logs whether TTS initialised.

**Effort:** half a day.

---

## Part 5 — WhatsApp messages

**Files:** new `tools/whatsapp_tools.py`, `data/contacts.json`, `config.py`

You have **no WhatsApp Desktop installed** (I checked `%LOCALAPPDATA%`), so
this will drive WhatsApp Web in your browser unless you install the desktop app
— which I'd recommend, it's much more reliable to automate.

### Two tiers, both worth having

**Tier 1 — deep link (default, robust).** Open
`https://wa.me/<number>?text=<url-encoded message>`. WhatsApp opens with the
recipient selected and the message pre-typed. Then either:
- stop there and let you press Enter (safest), or
- with `WHATSAPP_AUTOSEND=true`, focus the window and send `Enter` after
  `WHATSAPP_AUTOSEND_DELAY` seconds (default 8, for page load).

No dependencies, no login automation, survives WhatsApp UI changes.

**Tier 2 — `pywhatkit` (optional, add `pywhatkit>=5.4` to requirements).**
`sendwhatmsg_instantly()` fully automates WhatsApp Web. More capable, more
fragile — it breaks whenever WhatsApp reshuffles their DOM. Behind
`WHATSAPP_BACKEND=deeplink|pywhatkit`, defaulting to `deeplink`.

### Contacts

So you can say *"message mom"* rather than reciting a number:

`data/contacts.json` — `{"mom": "+9198XXXXXXXX", "sam": "+91..."}`, plus
`contact_add` / `contact_list` tools. Numbers stored in E.164 (with country
code, no spaces or `+` when passed to `wa.me`). Add `data/contacts.json` to
`.gitignore`.

### Safety — this one matters

Sending a message is an outward-facing action that can't be undone.

- `SafetyLevel.CONFIRM`, always. No `AGENT_AUTO_CONFIRM` exemption — I'd add an
  explicit override that ignores auto-confirm for outward-facing tools.
- The confirmation card must show **the recipient and the full message text**
  (this is what `confirm_summary` from Part 3 is for).
- `WHATSAPP_ALLOWED_NUMBERS` allow-list, defaulting to whatever is in
  `contacts.json`, so a hallucinated number can't be messaged.

**Tests:** URL construction and encoding (emoji, newlines, `&`), contact
resolution, unknown contact rejected, allow-list enforced, `pywhatkit` path
mocked.

**Effort:** 1 day for Tier 1 with contacts and safety; +half a day for Tier 2.

---

## Part 6 — Making calls on your phone

Straight answer first: **your PC cannot dial your phone by itself.** It needs a
bridge to the handset. There are three real options, and they differ a lot in
what they can do.

I checked your machine: **Phone Link is installed**, `adb` is not.

### Option A — ADB over USB or Wi-Fi (recommended, Android only)

The most capable and the most scriptable. One-time setup on your side:

1. Phone: Settings → About → tap Build number 7× → Developer options → enable
   **USB debugging**.
2. PC: install Android platform-tools, put `adb.exe` on PATH.
3. Plug in by USB, run `adb devices`, accept the pairing prompt on the phone.
4. For wireless: `adb tcpip 5555` then `adb connect <phone-ip>:5555`.

What that unlocks:

| Tool | Command |
|---|---|
| `phone_call` | `adb shell am start -a android.intent.action.CALL -d tel:+91...` |
| `phone_end_call` | `adb shell input keyevent 6` |
| `phone_sms` | `adb shell am start -a android.intent.action.SENDTO -d sms:...` + send key |
| `phone_whatsapp` | `adb shell am start -a android.intent.action.VIEW -d "https://wa.me/..."` |
| `phone_status` | `adb devices` — is the bridge alive |

This also gives you WhatsApp on the **actual phone** rather than WhatsApp Web,
which is a better answer to Part 5 if you go this route.

Caveat: the phone must be unlocked for the call intent to complete on most
Android versions. Wireless ADB drops when the phone changes network.

### Option B — Phone Link (already installed, no developer mode)

Windows' own Android integration; you may already have your phone paired. Alex
would launch it with the `ms-phone:` URI and drive its UI with pyautogui.

No public API, so this is screen automation — it breaks when Microsoft
redesigns the app, and it can't confirm the call actually connected. Reasonable
as a fallback when ADB isn't set up. Calls require your phone's Bluetooth in
range of the PC.

### Option C — Tasker + HTTP endpoint on the phone

Most reliable long-term: a tiny HTTP listener on the phone, Alex POSTs
`{"action":"call","number":"..."}`. Needs Tasker (paid) and setup time, but
once built it doesn't break, and it works over any network. Worth considering
if A and B both frustrate you.

### iPhone

Not possible. There's no equivalent of ADB, no automation API for placing
calls, and Apple's Continuity handoff only works from a Mac. If you're on
iPhone, the honest answer is that Parts 1–5 are achievable and Part 6 isn't.

### Design

`core/phone_bridge.py` with a small interface — `call`, `end_call`, `sms`,
`whatsapp`, `is_available` — and `AdbBridge` / `PhoneLinkBridge`
implementations selected by `PHONE_BRIDGE=adb|phonelink|none` (default `none`,
so nothing tries to run `adb` until you've set it up). `tools/phone_tools.py`
exposes the tools and returns a helpful "phone bridge isn't configured, here's
how" when it's off.

Safety, same as WhatsApp: `phone_call` and `phone_sms` are `CONFIRM`, exempt
from auto-confirm, and restricted by a `PHONE_ALLOWED_NUMBERS` allow-list.
A wrong number here is a real-world call to a stranger.

**Tests:** all offline — mock `subprocess.run`, assert the exact adb command
built for each action, test number normalisation to E.164, allow-list
enforcement, and the "bridge unavailable" message.

**Effort:** 1 day for the ADB bridge, +1 day for Phone Link, assuming setup
goes smoothly.

---

## What you need to do (I can't do these for you)

| # | Task | Needed for |
|---|---|---|
| 1 | Get a free Gemini API key and put it in `.env` | **Everything.** Fixes the 50% failure rate |
| 2 | Install Android platform-tools, enable USB debugging, pair the phone | Part 6 |
| 3 | Install WhatsApp Desktop (optional but recommended) | Part 5, more reliable than Web |
| 4 | Tell me whether your phone is Android or iPhone | Part 6 feasibility |

---

## Suggested order

| Step | Work | Effort | Why here |
|---|---|---|---|
| 1 | 1.1 LLM reliability | 0.5 d | Nothing else is testable until Alex reliably answers |
| 2 | 1.2 Window focus | 2 h | Fixes "I can't see anything"; every later feature needs it |
| 3 | Part 3 power polish + cache-bust | 0.5 d | Small, and unblocks the approval card for everything dangerous |
| 4 | Part 2 YouTube | 1 d | Highest daily value, no external setup |
| 5 | Part 4 startup greeting | 0.5 d | Self-contained, no dependencies |
| 6 | Part 5 WhatsApp Tier 1 | 1 d | Needs the `confirm_summary` from step 3 |
| 7 | Part 6 ADB bridge | 1 d | Gated on your setup tasks |
| 8 | Part 6 Phone Link fallback | 1 d | Only if ADB proves awkward |

Steps 1–5 need nothing from you but the Gemini key. Roughly a week of
part-time work to the end of step 6.

---

## Cross-cutting work these all share

- **`confirm_summary` on `ToolSpec`** — human-readable confirmation text. Built
  in Part 3, used by Parts 5 and 6.
- **Outward-facing safety class** — a flag meaning "`AGENT_AUTO_CONFIRM` must
  not apply". Messages and calls reach other people; approval must be per-use.
- **Allow-lists** — `WHATSAPP_ALLOWED_NUMBERS` and `PHONE_ALLOWED_NUMBERS`
  mirroring the existing `ALLOWED_FILE_PATHS` pattern.
- **`.env.example` and README** updated as each part lands.
- **Every new tool needs `examples=[...]`** so the LLM picks it over the generic
  `web_open` — this is why "play X on YouTube" currently gets a search page.
