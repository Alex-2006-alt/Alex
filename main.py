"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║     █████╗ ██╗     ███████╗██╗  ██╗                          ║
║    ██╔══██╗██║     ██╔════╝╚██╗██╔╝                          ║
║    ███████║██║     █████╗   ╚███╔╝                           ║
║    ██╔══██║██║     ██╔══╝   ██╔██╗                           ║
║    ██║  ██║███████╗███████╗██╔╝ ██╗                          ║
║    ╚═╝  ╚═╝╚══════╝╚══════╝╚═╝  ╚═╝                        ║
║                                                              ║
║    Personal AI Assistant — Listen, Talk, Control Your PC     ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python main.py                  # Start with wake word ("Hey Alex")
    python main.py --no-wake-word   # Always listening (no wake word needed)
    python main.py --text           # Text-only mode (type commands, no mic)
    python main.py --server         # Start JARVIS web interface (browser)
    python main.py --test           # Run diagnostic tests
"""

import sys
import argparse

# Ensure the project root is in the Python path
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from utils.logger import log
import config


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=f"{config.ASSISTANT_NAME} — Personal AI Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-wake-word",
        action="store_true",
        help="Disable wake word — always listen for commands",
    )
    parser.add_argument(
        "--text",
        action="store_true",
        help="Text-only mode — type commands instead of speaking",
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Start the JARVIS web interface (open in browser)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for the web server (default: 5000)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run diagnostic tests on all modules",
    )
    return parser.parse_args()


def run_text_mode():
    """Run in text-only mode — type commands instead of speaking."""
    from core.assistant import Assistant

    assistant = Assistant(use_wake_word=False, input_mode="text")
    assistant.run()



def run_diagnostic_tests():
    """Run quick tests on all modules to verify they work."""
    print(f"\n{'='*60}")
    print(f"  🧪 {config.ASSISTANT_NAME} — Diagnostic Tests")
    print(f"{'='*60}\n")

    tests_passed = 0
    tests_failed = 0

    # Test 1: Config
    print("  [1/6] Testing configuration...")
    try:
        assert config.ASSISTANT_NAME, "Assistant name not set"
        assert config.WHISPER_MODEL_SIZE in ("tiny", "base", "small", "medium", "large")
        print(f"    ✅ Config OK — Name: {config.ASSISTANT_NAME}, LLM: {config.LLM_PROVIDER}")
        tests_passed += 1
    except Exception as e:
        print(f"    ❌ Config FAILED: {e}")
        tests_failed += 1

    # Test 2: Logger
    print("  [2/6] Testing logger...")
    try:
        from utils.logger import log
        log.info("Logger test — this should appear with color")
        print("    ✅ Logger OK")
        tests_passed += 1
    except Exception as e:
        print(f"    ❌ Logger FAILED: {e}")
        tests_failed += 1

    # Test 3: System info
    print("  [3/6] Testing system info...")
    try:
        from utils.system_info import get_system_summary
        info = get_system_summary()
        print(f"    ✅ System Info OK — OS: {info['os']}, RAM: {info['ram_total_gb']}GB, CPU: {info['cpu_cores_logical']} cores")
        tests_passed += 1
    except Exception as e:
        print(f"    ❌ System Info FAILED: {e}")
        tests_failed += 1

    # Test 4: Speaker (TTS)
    print("  [4/6] Testing text-to-speech...")
    try:
        from core.speaker import Speaker
        speaker = Speaker()
        speaker.say("Test. Alex is working.", block=True)
        print("    ✅ TTS OK — Did you hear the test speech?")
        tests_passed += 1
    except Exception as e:
        print(f"    ❌ TTS FAILED: {e}")
        tests_failed += 1

    # Test 5: Audio devices
    print("  [5/6] Testing audio devices...")
    try:
        from utils.audio_utils import list_audio_devices
        devices = list_audio_devices()
        if devices:
            print(f"    ✅ Audio OK — Found {len(devices)} input device(s)")
            tests_passed += 1
        else:
            print("    ⚠️ No audio input devices found!")
            tests_failed += 1
    except Exception as e:
        print(f"    ❌ Audio FAILED: {e}")
        tests_failed += 1

    # Test 6: Brain connectivity
    print("  [6/6] Testing AI brain...")
    try:
        from core.brain import Brain
        brain = Brain()
        if config.LLM_PROVIDER == "gemini" and not config.GEMINI_API_KEY:
            print("    ⚠️ Brain SKIPPED — GEMINI_API_KEY not set in .env")
        elif config.LLM_PROVIDER == "openai" and not config.OPENAI_API_KEY:
            print("    ⚠️ Brain SKIPPED — OPENAI_API_KEY not set in .env")
        else:
            result = brain.think("Say hello in one short sentence.")
            print(f"    ✅ Brain OK — Response: \"{result['response'][:60]}\"")
            tests_passed += 1
    except Exception as e:
        print(f"    ❌ Brain FAILED: {e}")
        tests_failed += 1

    # Summary
    total = tests_passed + tests_failed
    print(f"\n{'='*60}")
    print(f"  Results: {tests_passed}/{total} passed, {tests_failed}/{total} failed")
    if tests_failed == 0:
        print(f"  🎉 All tests passed! {config.ASSISTANT_NAME} is ready to go!")
    else:
        print(f"  ⚠️ Some tests failed. Check the errors above.")
    print(f"{'='*60}\n")


def run_server_mode(port: int = 5000):
    """Run the JARVIS web interface with the Flask API server."""
    try:
        from server import app
        import threading
        import time
        import webbrowser

        print(f"\n{'='*60}")
        print(f"  🌐 {config.ASSISTANT_NAME} — JARVIS Web Interface")
        print(f"  Opening http://127.0.0.1:{port} in your browser...")
        print(f"  ⛔ Press Ctrl+C to stop")
        print(f"{'='*60}\n")

        # Open browser after a short delay
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://127.0.0.1:{port}")

        threading.Thread(target=open_browser, daemon=True).start()

        app.run(host="127.0.0.1", port=port, debug=False)

    except ImportError as e:
        print(f"\n  ❌ Missing dependency: {e}")
        print(f"  Run: pip install flask flask-cors\n")
    except Exception as e:
        print(f"\n  ❌ Server error: {e}\n")


def main():
    """Main entry point."""
    args = parse_args()

    if args.test:
        run_diagnostic_tests()
        return

    if args.text:
        run_text_mode()
        return

    if args.server:
        run_server_mode(args.port)
        return

    # Normal voice mode
    try:
        from core.assistant import Assistant
        assistant = Assistant(use_wake_word=not args.no_wake_word)
        assistant.run()
    except KeyboardInterrupt:
        log.info("Interrupted by user")
    except Exception as e:
        log.critical(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    main()
