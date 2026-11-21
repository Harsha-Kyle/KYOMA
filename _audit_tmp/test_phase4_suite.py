"""
test_phase4_suite.py — Extended real-input test suite for KYOMA Phase 4
Tests all 10 missing/extended phrases, clean vs simulated Whisper-transcribed,
and includes the 6-turn context contamination chain.
"""

import sys
import os
import time
import json
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
KYOMA_DIR = os.path.join(REPO_ROOT, "Kyoma")
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")

if KYOMA_DIR not in sys.path:
    sys.path.insert(0, KYOMA_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ["KYOMA_DEMO_MODE"] = "1"

from fast_router import route
from tts_sanitizer import sanitize_for_tts
from reminder_utils import reset_demo_reminders

# Phase 4 required missing phrases:
# 1. "Hey Kyoma, remind me to drink water in one minute."
# 2. "What is the time, date and battery level?"
# 3. "Increase brightness to 60 percent and volume to 80 percent."
# 4. "what all you can do?"
# 5. "increase brightness for me."
# 6. "take a SS and save it as Kyoma"
# 7. "what is the status?"
# 8. "you sit, remind you to drink water"
# 9. "Increase brightness and volume"
# 10. "60% and 80%"

TEST_CASES = [
    {
        "phrase": "Hey Kyoma, remind me to drink water in one minute.",
        "type": "clean",
        "description": "Natural wake-word prefix + natural number reminder"
    },
    {
        "phrase": "What is the time, date and battery level?",
        "type": "clean",
        "description": "Compound multi-system info query"
    },
    {
        "phrase": "Increase brightness to 60 percent and volume to 80 percent.",
        "type": "clean",
        "description": "Compound brightness + volume setting"
    },
    {
        "phrase": "what all you can do?",
        "type": "clean",
        "description": "Capabilities query variant"
    },
    {
        "phrase": "increase brightness for me.",
        "type": "clean",
        "description": "Brightness up with polite suffix"
    },
    {
        "phrase": "take a SS and save it as Kyoma",
        "type": "clean",
        "description": "Screenshot with custom filename"
    },
    {
        "phrase": "what is the status?",
        "type": "clean",
        "description": "System status check"
    },
    {
        "phrase": "you sit, remind you to drink water",
        "type": "whisper_transcribed",
        "description": "Whisper audio hallucination / garbled input (expected fall-through or refusal)"
    },
    {
        "phrase": "Increase brightness and volume",
        "type": "clean",
        "description": "Shared action compound command"
    },
    {
        "phrase": "60% and 80%",
        "type": "whisper_transcribed",
        "description": "Fragmentary input without action (expected no match / fall-through)"
    }
]

def run_suite():
    print("=" * 70)
    print("KYOMA PHASE 4: EXTENDED REAL-INPUT TEST SUITE")
    print("=" * 70)
    reset_demo_reminders()

    results = []
    for idx, tc in enumerate(TEST_CASES, 1):
        phrase = tc["phrase"]
        tc_type = tc["type"]
        t0 = time.perf_counter()
        
        # Test fast_router path directly
        spoken, handled = route(phrase)
        latency = time.perf_counter() - t0
        
        route_name = "fast_router" if handled else "fallthrough_to_llm"
        spoken_clean = sanitize_for_tts(spoken or "")
        word_count = len(spoken_clean.split())
        
        # Check constraints
        pass_25_words = word_count <= 25
        no_dot_and = ". and" not in spoken_clean.lower()
        
        rec = {
            "index": idx,
            "phrase": phrase,
            "type": tc_type,
            "route": route_name,
            "latency_s": round(latency, 4),
            "spoken_output": spoken_clean,
            "word_count": word_count,
            "passes_25_words": pass_25_words,
            "no_dot_and": no_dot_and,
            "error": None
        }
        results.append(rec)
        
        print(f"\n[{idx}/10] {tc_type.upper()} | '{phrase}'")
        print(f"  Route: {route_name} | Latency: {latency:.4f}s | Words: {word_count}")
        print(f"  Spoken: {spoken_clean!r}")
        print(f"  Checks: <=25 words: {pass_25_words} | No '. and': {no_dot_and}")

    # =========================================================================
    # Scripted 6-Turn Conversation: Reminder Refusal & Context Contamination Test
    # =========================================================================
    print("\n" + "=" * 70)
    print("SCRIPTED 6-TURN CONVERSATION: LEAKAGE & CONTAMINATION AUDIT")
    print("=" * 70)
    
    from memory_manager import MemoryManager
    mem = MemoryManager(max_history=6)
    
    scripted_turns = [
        ("Turn 1 (Refusal probe): Lock the screen please.", "fast_router / refusal check"),
        ("Turn 2 (Normal command): What time is it?", "fast_router time"),
        ("Turn 3 (Refusal probe): Close all applications.", "refusal check"),
        ("Turn 4 (Normal command): Set volume to 50 percent.", "fast_router volume"),
        ("Turn 5 (Garbled fragment): 60% and 80%", "fallthrough fragment"),
        ("Turn 6 (Query): Tell me the date.", "fast_router date")
    ]
    
    turn_results = []
    for t_idx, (turn_input, desc) in enumerate(scripted_turns, 1):
        clean_input = turn_input.split(": ")[-1]
        t0 = time.perf_counter()
        spoken, handled = route(clean_input)
        latency = time.perf_counter() - t0
        
        mem.add_user_message(clean_input)
        if handled:
            mem.add_assistant_message(spoken)
            
        # Check contamination
        recent_history = mem.get_messages()
        contaminated = False
        if handled and spoken:
            if "disabled" in spoken.lower() and t_idx in (2, 4, 6):
                contaminated = True
                
        turn_results.append({
            "turn": t_idx,
            "input": clean_input,
            "route": "fast_router" if handled else "fallthrough",
            "latency_s": round(latency, 4),
            "output": spoken,
            "contaminated": contaminated
        })
        print(f"[{t_idx}/6] '{clean_input}' -> {spoken!r} (Contaminated: {contaminated})")

    out_file = os.path.join(REPO_ROOT, "_audit_tmp", "phase4_suite_results.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({"test_cases": results, "conversation_turns": turn_results}, f, indent=2)
    print(f"\nAll results saved to: {out_file}")
    return results, turn_results

if __name__ == "__main__":
    run_suite()
