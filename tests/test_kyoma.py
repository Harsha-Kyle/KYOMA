"""Consolidated Kyoma test runner supporting --offline, --backend, --internet, and --all modes."""

import argparse
import runpy
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE_ROOT = REPO_ROOT.parent
BACKEND_DIR = REPO_ROOT / "backend"
KYOMA_DIR = REPO_ROOT / "Kyoma"

for p in (str(REPO_ROOT), str(BACKEND_DIR), str(KYOMA_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

OFFLINE_SUITES = [
    ("test_media_suite", WORKSPACE_ROOT / "test_media_suite.py"),
    ("test_pending_target_suite", WORKSPACE_ROOT / "test_pending_target_suite.py"),
    ("test_reminders_suite", WORKSPACE_ROOT / "test_reminders_suite.py"),
    ("test_tts_suite", WORKSPACE_ROOT / "test_tts_suite.py"),
    ("test_vad_suite", WORKSPACE_ROOT / "test_vad_suite.py"),
    ("test_demo_runner", REPO_ROOT / "test_demo_runner.py"),
]

BACKEND_SUITES = [
    ("test_chat_suite", WORKSPACE_ROOT / "test_chat_suite.py"),
    ("test_settings", WORKSPACE_ROOT / "test_settings.py"),
]

INTERNET_SUITES = [
    ("test_search_suite", WORKSPACE_ROOT / "test_search_suite.py"),
]


def run_suite(name: str, path: Path) -> bool:
    print(f"\n{'=' * 60}\n[RUN] {name} ({path.name})\n{'=' * 60}")
    if not path.exists():
        print(f"[FAIL] {name}: File not found at {path}")
        return False
    try:
        runpy.run_path(str(path), run_name="__main__")
        print(f"[PASS] {name}")
        return True
    except SystemExit as exc:
        ok = exc.code in (0, None)
        print(f"[{'PASS' if ok else 'FAIL'}] {name} (SystemExit: {exc.code})")
        return ok
    except Exception:
        traceback.print_exc()
        print(f"[FAIL] {name}")
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Consolidated Kyoma Test Suite")
    parser.add_argument("--offline", action="store_true", help="Run offline suites (default)")
    parser.add_argument("--backend", action="store_true", help="Run live backend suites")
    parser.add_argument("--internet", action="store_true", help="Run internet-dependent suites")
    parser.add_argument("--all", action="store_true", help="Run all 9 suites")
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

    results = [(name, run_suite(name, path)) for name, path in selected]
    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed

    print(f"\n{'=' * 60}\nSUMMARY: {passed}/{len(results)} passed, {failed} failed\n{'=' * 60}")
    for name, ok in results:
        print(f"  - {name}: {'PASS' if ok else 'FAIL'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
