"""
ALEX -- Web API Server
Flask server that bridges the JARVIS GUI with the Python backend.

Usage:
    python server.py               # Start server on port 5000
    python server.py --port 8080   # Custom port
"""

import sys
import threading
import time
import uuid
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

from utils.logger import log
import config

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="gui", static_url_path="/")
CORS(app)

# ── Lazy-loaded assistant ─────────────────────────────────────────────────────
_assistant = None
_boot_status = {"stage": "starting", "steps": [], "ready": False}

# Seconds to wait on a chat request before calling it slow. Extended
# automatically while the user has an unanswered confirmation card.
CHAT_TIMEOUT = 60


def _get_assistant():
    global _assistant
    if _assistant is None:
        from core.assistant import Assistant
        _boot_status["stage"] = "loading"
        _boot_status["steps"].append("Loading ALEX assistant...")
        _assistant = Assistant(use_wake_word=False, input_mode="api")
        _boot_status["stage"] = "ready"
        _boot_status["ready"] = True
        _boot_status["steps"].append("All systems nominal. ALEX is online.")
    return _assistant


# ── Pending confirmations ─────────────────────────────────────────────────────
#
# CONFIRM-level tools (shell_run, system_power, file_delete, process_kill,
# code_run) are denied by ToolRegistry unless the caller can ask the user. HTTP
# has no way to ask mid-request, so a request that hits one parks a pending
# confirmation here and blocks on its Event. The browser polls
# GET /api/confirmations, shows an approve/deny card, and POSTs /api/confirm,
# which sets the Event and lets the original request continue.

_pending: dict[str, dict] = {}
_pending_lock = threading.Lock()


def _expire_stale():
    """Drop confirmations nobody answered in time."""
    now = time.time()
    with _pending_lock:
        for cid, entry in list(_pending.items()):
            if now - entry["created"] > config.CONFIRMATION_TIMEOUT:
                entry["approved"] = False
                entry["event"].set()
                _pending.pop(cid, None)


def _request_confirmation(tool_name: str, params: dict) -> bool:
    """
    Park a confirmation request and block until the browser answers it.

    Used as the ``confirm_callback`` for web requests. Returns False on
    timeout — an unanswered prompt is a denial, never an approval.
    """
    _expire_stale()

    cid = uuid.uuid4().hex[:12]
    entry = {
        "id": cid,
        "tool": tool_name,
        "params": params,
        "created": time.time(),
        "event": threading.Event(),
        "approved": False,
    }
    with _pending_lock:
        _pending[cid] = entry

    log.warning(f"⏸️ Awaiting confirmation for '{tool_name}' (id={cid})")

    answered = entry["event"].wait(timeout=config.CONFIRMATION_TIMEOUT)
    with _pending_lock:
        _pending.pop(cid, None)

    if not answered:
        log.warning(f"⌛ Confirmation for '{tool_name}' timed out — denying")
        return False

    log.info(f"{'✅ Approved' if entry['approved'] else '🚫 Denied'}: {tool_name} (id={cid})")
    return bool(entry["approved"])


def _has_pending() -> bool:
    _expire_stale()
    with _pending_lock:
        return bool(_pending)


# ── System Stats ──────────────────────────────────────────────────────────────
def _get_system_stats():
    try:
        import psutil

        cpu = psutil.cpu_percent(interval=0.5)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        battery = psutil.sensors_battery()
        net = psutil.net_if_addrs()

        if battery:
            batt_pct = round(battery.percent)
            batt_status = "Charging" if battery.power_plugged else "On Battery"
            if batt_pct > 95 and battery.power_plugged:
                batt_status = "Full"
        else:
            batt_pct = 100
            batt_status = "AC Power"

        ip_addr = "Not connected"
        for iface, addrs in net.items():
            if iface.lower() in ("loopback", "lo"):
                continue
            for addr in addrs:
                if addr.family.name == "AF_INET" and not addr.address.startswith("127."):
                    ip_addr = addr.address
                    break

        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
        h, rem = divmod(int(uptime), 3600)
        m, s = divmod(rem, 60)

        return {
            "cpu": cpu,
            "ram_percent": mem.percent,
            "ram_used": round(mem.used / 1e9, 1),
            "ram_total": round(mem.total / 1e9, 1),
            "disk_percent": round(disk.percent),
            "disk_free": round(disk.free / 1e9),
            "battery_percent": batt_pct,
            "battery_status": batt_status,
            "network_ip": ip_addr,
            "uptime": f"{h:02d}:{m:02d}:{s:02d}",
        }
    except Exception as e:
        log.error(f"System stats error: {e}")
        return None


# =============================================================================
#  API ROUTES
# =============================================================================

@app.route("/")
def index():
    return send_from_directory("gui", "index.html")


@app.route("/api/status")
def api_status():
    stats = _get_system_stats()
    return jsonify({
        "status": "online",
        "assistant_name": config.ASSISTANT_NAME,
        "llm_provider": config.LLM_PROVIDER.upper(),
        "llm_model": getattr(config, f"{config.LLM_PROVIDER.upper()}_MODEL", "unknown"),
        "stt_engine": f"WHISPER {config.WHISPER_MODEL_SIZE.upper()}",
        "tts_engine": config.TTS_ENGINE.upper(),
        "wake_word": config.WAKE_WORD.upper(),
        "agent_mode": config.AGENT_MODE,
        "boot": _boot_status,
        "system_stats": stats,
    })


@app.route("/api/stats")
def api_stats():
    stats = _get_system_stats()
    if stats:
        return jsonify(stats)
    return jsonify({"error": "psutil not available"}), 500


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json()
    if not data or "message" not in data:
        return jsonify({"error": "No message provided"}), 400

    message = data["message"].strip()
    if not message:
        return jsonify({"error": "Empty message"}), 400

    log.info(f"API chat: \"{message}\"")

    result_holder = {"full_res": None, "error": None}

    def _process():
        try:
            assistant = _get_assistant()
            res = assistant.process_text_full(message, confirm_callback=_request_confirmation)
            result_holder["full_res"] = res
        except Exception as e:
            result_holder["error"] = str(e)

    worker = threading.Thread(target=_process, daemon=True)
    worker.start()
    worker.join(timeout=CHAT_TIMEOUT)

    # Don't call a request slow when it's actually waiting on the user: keep
    # extending while a confirmation card is still on screen unanswered.
    waited = CHAT_TIMEOUT
    while worker.is_alive() and _has_pending() and waited < CHAT_TIMEOUT + config.CONFIRMATION_TIMEOUT:
        worker.join(timeout=5)
        waited += 5

    if worker.is_alive():
        log.error(f"Chat request timed out after {waited}s: \"{message}\"")
        return jsonify({
            "error": "Request timed out",
            "response": "Sorry, that request took too long. Please try again with a simpler request.",
        }), 504

    if result_holder["error"]:
        log.error(f"Chat error: {result_holder['error']}")
        return jsonify({
            "error": result_holder["error"],
            "response": f"Sorry, I encountered an error: {result_holder['error']}",
        }), 500

    full = result_holder["full_res"] or {}
    return jsonify({
        "response": full.get("response") or "I'm sorry, I couldn't generate a response.",
        "action": full.get("action"),
        "params": full.get("params"),
        "action_result": full.get("action_result"),
        "plan": full.get("plan"),
        "timestamp": time.time(),
    })


@app.route("/api/confirmations")
def api_confirmations_list():
    """Confirmations waiting on the user. The GUI polls this."""
    _expire_stale()
    with _pending_lock:
        pending = [
            {
                "id": e["id"],
                "tool": e["tool"],
                "params": e["params"],
                "expires_in": max(0, round(config.CONFIRMATION_TIMEOUT - (time.time() - e["created"]))),
            }
            for e in _pending.values()
        ]
    return jsonify({"pending": pending, "count": len(pending)})


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    """Approve or deny a pending confirmation, unblocking its request."""
    data = request.get_json() or {}
    cid = data.get("confirmation_id")
    if not cid:
        return jsonify({"error": "confirmation_id required"}), 400

    approved = bool(data.get("approved", False))

    with _pending_lock:
        entry = _pending.get(cid)
        if entry is None:
            return jsonify({"error": "Unknown or expired confirmation", "confirmation_id": cid}), 404
        entry["approved"] = approved
        entry["event"].set()

    return jsonify({"confirmation_id": cid, "approved": approved})


@app.route("/api/action", methods=["POST"])
def api_action():
    data = request.get_json()
    if not data or "action" not in data:
        return jsonify({"error": "No action provided"}), 400

    action = data["action"]
    params = data.get("params", {})
    log.info(f"API action: {action}")

    try:
        assistant = _get_assistant()
        if not assistant._tool_registry:
            return jsonify({"error": "ToolRegistry is not initialized"}), 503
        # Same gate as chat: a CONFIRM-level tool asks the browser first.
        result = assistant._tool_registry.execute(
            action, params, confirm_callback=_request_confirmation
        )
        return jsonify({"result": result.to_response(), "success": result.success, "action": action})
    except Exception as e:
        log.error(f"Action error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/actions")
def api_actions():
    try:
        assistant = _get_assistant()
        if not assistant._tool_registry:
            return jsonify({"error": "ToolRegistry is not initialized"}), 503
        tools = assistant._tool_registry.list_tools()
        by_cat = assistant._tool_registry.list_by_category()
        return jsonify({"tools": tools, "count": len(tools), "by_category": by_cat})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/plugins")
def api_plugins():
    try:
        from plugins.plugin_loader import PluginLoader
        loader = PluginLoader()
        loader.discover()
        plugin_list = loader.list_plugins()
        return jsonify({"plugins": plugin_list, "count": len(plugin_list)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Memory API ────────────────────────────────────────────────────────────────

@app.route("/api/memory")
def api_memory_get():
    try:
        assistant = _get_assistant()
        if not hasattr(assistant, "_memory") or not assistant._memory:
            return jsonify({"facts": [], "stats": {}})
        category = request.args.get("category")
        facts = assistant._memory.get_all_facts(category=category)
        stats = assistant._memory.stats()
        return jsonify({
            "facts": [{"key": f.key, "value": f.value, "category": f.category, "confidence": f.confidence} for f in facts],
            "stats": stats,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memory/<key>", methods=["DELETE"])
def api_memory_delete(key):
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "_memory") and assistant._memory:
            deleted = assistant._memory.forget(key)
            return jsonify({"deleted": deleted, "key": key})
        return jsonify({"error": "Memory not available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/memory", methods=["POST"])
def api_memory_set():
    data = request.get_json()
    if not data or "key" not in data or "value" not in data:
        return jsonify({"error": "key and value required"}), 400
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "_memory") and assistant._memory:
            assistant._memory.remember(
                key=data["key"],
                value=data["value"],
                category=data.get("category", "general"),
            )
            return jsonify({"stored": True})
        return jsonify({"error": "Memory not available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Tasks API ─────────────────────────────────────────────────────────────────

@app.route("/api/tasks")
def api_tasks_list():
    try:
        assistant = _get_assistant()
        if not hasattr(assistant, "_task_manager") or not assistant._task_manager:
            return jsonify({"tasks": []})
        include_done = request.args.get("include_done", "false").lower() == "true"
        tasks = assistant._task_manager.list_tasks(include_done=include_done)
        return jsonify({"tasks": [t.to_dict() for t in tasks], "count": len(tasks)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def api_task_cancel(task_id):
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "_task_manager") and assistant._task_manager:
            cancelled = assistant._task_manager.cancel(task_id)
            return jsonify({"cancelled": cancelled, "task_id": task_id})
        return jsonify({"error": "TaskManager not available"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Plan + Status APIs ────────────────────────────────────────────────────────

@app.route("/api/plan")
def api_plan_current():
    try:
        assistant = _get_assistant()
        plan = assistant.brain.get_current_plan()
        if plan:
            return jsonify(plan)
        return jsonify({"status": "idle", "message": "No active plan"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/assistant-status")
def api_assistant_status():
    try:
        assistant = _get_assistant()
        return jsonify(assistant.get_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/task-history")
def api_task_history():
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "_memory") and assistant._memory:
            limit = int(request.args.get("limit", 10))
            history = assistant._memory.get_task_history(limit=limit)
            return jsonify({"history": history})
        return jsonify({"history": []})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =============================================================================
#  MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="ALEX Web API Server")
    parser.add_argument("--port", type=int, default=5000, help="Port to run on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    args = parser.parse_args()

    llm_model = getattr(config, f"{config.LLM_PROVIDER.upper()}_MODEL", "unknown")
    print("=" * 62)
    print("  ALEX -- Advanced Personal AI Assistant  |  Web Server Mode")
    print("=" * 62)
    print(f"  Interface : http://{args.host}:{args.port}")
    print(f"  LLM       : {config.LLM_PROVIDER} ({llm_model})")
    print(f"  STT       : Whisper ({config.WHISPER_MODEL_SIZE})")
    print(f"  TTS       : {config.TTS_ENGINE}")
    print(f"  Agent Mode: {config.AGENT_MODE}")
    print("  Press Ctrl+C to stop")
    print("=" * 62)
    print()

    def preload():
        time.sleep(1)
        try:
            _get_assistant()
            log.info("Assistant pre-loaded successfully")
        except Exception as e:
            log.error(f"Failed to pre-load assistant: {e}")

    threading.Thread(target=preload, daemon=True).start()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
