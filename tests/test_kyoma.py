"""Consolidated, self-contained Kyoma test suite.

Supports:
  --offline   Run offline unit/regression suites (default)
  --backend   Run live backend HTTP API suites (http://127.0.0.1:8000)
  --internet  Run internet-dependent live search suite
  --all       Run all suites
"""

import argparse
import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
KYOMA_DIR = REPO_ROOT / "Kyoma"

for p in (str(REPO_ROOT), str(BACKEND_DIR), str(KYOMA_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)


def test_media_suite() -> None:
    import fast_router

    phrases = [
        "Hey Kyoma, play",
        "Hey Kyoma, continue the song",
        "Hey Kyoma, skip this",
        "Hey Kyoma, next",
        "Hey Kyoma, previous track",
        "Hey Kyoma, play the video again",
        "Hey Kyoma, restart song",
    ]
    for phrase in phrases:
        matched, resp = fast_router.route(phrase)
        assert matched, f"Expected route match for: {phrase}"
        print(f"  '{phrase}' -> {resp}")


def test_pending_target_suite() -> None:
    import fast_router
    import pending_actions

    pending_actions.clear_pending_action()
    m1, _ = fast_router.route("Hey Kyoma, set brightness to 70")
    assert m1, "Expected brightness route"
    m2, _ = fast_router.route("what time is it")
    assert m2, "Expected time route"
    m3, _ = fast_router.route("70")
    assert not m3, "Bare '70' without pending action should not match"


def test_reminders_suite() -> None:
    import fast_router
    import reminder_utils

    matched, _ = fast_router.route("Hey Kyoma, list my reminders")
    assert matched, "Expected reminder list route"
    active = reminder_utils.get_active_reminders()
    assert isinstance(active, list), "Expected list from get_active_reminders()"


def test_tts_suite() -> None:
    import tts_sanitizer

    cleaned = tts_sanitizer.sanitize_for_tts("**Hello** [world](https://example.com) at 10:00 AM!")
    assert "**" not in cleaned and "https://" not in cleaned
    assert "10:00" in cleaned


def test_vad_suite() -> None:
    import fast_router
    from services.Input.Input import WAKE_WORD_PATTERN, VoiceInput

    valid_wakes = ["Hey Kyoma", "hey kyoma, what time is it", "Kyoma please"]
    for w in valid_wakes:
        assert WAKE_WORD_PATTERN.search(w), f"Expected wake match for: {w}"
    assert len(VoiceInput.whisper_filter_list) >= 10

    m, _ = fast_router.route("Hey Kyoma, what time is it?")
    assert m


def test_demo_runner() -> None:
    import fast_router

    os.environ["KYOMA_DEMO_MODE"] = "1"
    phrases = [
        "What time is it?",
        "Open Calculator.",
        "Set volume to 50.",
    ]
    for p in phrases:
        m, _ = fast_router.route(p)
        assert m, f"Demo phrase failed: {p}"


def _http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return 0, ""


def test_backend_settings() -> None:
    status, body = _http_get("http://127.0.0.1:8000/api/settings")
    assert status == 200, f"Backend /api/settings returned status {status} (is server running?)"
    data = json.loads(body)
    assert isinstance(data, dict)


def test_backend_chat() -> None:
    status, _ = _http_get("http://127.0.0.1:8000/api/startup/status")
    assert status == 200, f"Backend /api/startup/status returned status {status} (is server running?)"


def test_internet_search() -> None:
    import search_evidence

    res = search_evidence.search_web_evidence("current Prime Minister of India", timeout=8.0)
    assert isinstance(res, dict) and res.get("ok") is True, f"Live search failed: {res}"


OFFLINE_SUITES = [
    ("test_media_suite", test_media_suite),
    ("test_pending_target_suite", test_pending_target_suite),
    ("test_reminders_suite", test_reminders_suite),
    ("test_tts_suite", test_tts_suite),
    ("test_vad_suite", test_vad_suite),
    ("test_demo_runner", test_demo_runner),
]

BACKEND_SUITES = [
    ("test_backend_settings", test_backend_settings),
    ("test_backend_chat", test_backend_chat),
]

INTERNET_SUITES = [
    ("test_internet_search", test_internet_search),
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidated Kyoma Test Suite")
    parser.add_argument("--offline", action="store_true", help="Run offline suites (default)")
    parser.add_argument("--backend", action="store_true", help="Run live backend suites")
    parser.add_argument("--internet", action="store_true", help="Run internet-dependent suites")
    parser.add_argument("--all", action="store_true", help="Run all suites")
    args = parser.parse_args()

    selected = []
    if args.all:
        selected = OFFLINE_SUITES + BACKEND_SUITES + INTERNET_SUITES
    else:
        if args.offline or not (args.backend or args.internet):
            selected.extend(OFFLINE_SUITES)
        if args.backend:
            selected.extend(BACKEND_SUITES)
        if args.internet:
            selected.extend(INTERNET_SUITES)

    passed = 0
    failed = 0
    for name, fn in selected:
        t0 = time.perf_counter()
        print(f"\n[RUN] {name}")
        try:
            fn()
            dt = time.perf_counter() - t0
            print(f"[PASS] {name} ({dt:.2f}s)")
            passed += 1
        except Exception:
            traceback.print_exc()
            print(f"[FAIL] {name}")
            failed += 1

    print(f"\nSUMMARY: {passed}/{len(selected)} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
