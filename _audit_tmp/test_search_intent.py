"""
Unit test for is_search_query() and _check_connectivity().
Run from: LocalAIVtuber2-master/
"""
import sys, os
sys.path.insert(0, 'Kyoma')
sys.stdout.reconfigure(encoding='utf-8')

from ollama_workflow import is_search_query, _check_connectivity

should_match = [
    "who is the prime minister of India",
    "who was Albert Einstein",
    "what is the current price of Bitcoin",
    "what's the current weather in Delhi",
    "search for best Python tutorials",
    "look up the latest news",
    "find out what happened to the stock market",
    "latest news about AI",
    "news about Ukraine",
    "what happened to Twitter",
    "tell me about the Eiffel Tower",
    "find out who won the 2024 election",
]

should_not_match = [
    "what time is it",
    "what is the battery level",
    "open youtube",
    "volume up",
    "play music",
    "set brightness to 80",
    "take a screenshot",
    "lock the screen",
    "mute",
    "check network status",
    "remind me at 5pm",
    "launch notepad",
    "hello how are you",
    "tell me a joke",
    "what can you do",
    "next track",
    "skip",
    "who is calling",
    "who is there",
    "search",
    "hi",
]

passed = failed = 0
print("=== is_search_query() tests ===")
for q in should_match:
    result = is_search_query(q)
    ok = result is True
    status = "PASS" if ok else "FAIL"
    if not ok: failed += 1
    else: passed += 1
    print(f"  [{status}] MATCH    | {q!r}")

for q in should_not_match:
    result = is_search_query(q)
    ok = result is False
    status = "PASS" if ok else "FAIL"
    if not ok: failed += 1
    else: passed += 1
    print(f"  [{status}] NO-MATCH | {q!r}")

print(f"\nResult: {passed}/{passed+failed} passed, {failed} failed")

print("\n=== _check_connectivity() ===")
online = _check_connectivity(timeout=2.0)
print(f"  Online: {online}")

if failed > 0:
    sys.exit(1)
