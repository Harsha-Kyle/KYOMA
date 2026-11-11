"""
test_demo_runner.py — Repeatable test runner for KYOMA Phase 3
Uses the exact application path as /api/completion (KyomaLLM / LLM.get_completion),
with actual audio/TTS playback mocked, and isolates user data.
"""

import sys
import os
import time
import json
import re

# Set up paths
REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
KYOMA_DIR = os.path.join(REPO_ROOT, "Kyoma")
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")

if KYOMA_DIR not in sys.path:
    sys.path.insert(0, KYOMA_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Force demo mode
os.environ["KYOMA_DEMO_MODE"] = "1"

# Import LLM service
from services.LLM.LLM import LLM

# The 15 test phrases from Section 1 of the specification
TEST_PHRASES = [
    "What all can you do?",
    "What is the status?",
    "Tell me the time and date.",
    "Time and battery.",
    "Take a SS and save it as Kyoma.",
    "Take a screenshot.",
    "Set a reminder in 1 minute to drink water.",
    "Remind me to submit assignment in 2 minutes.",
    "List my reminders.",
    "Increase brightness and volume.",
    "Set brightness to 60 and volume to 80.",
    "How are you?",
    "Who are you?",
    "Open Notepad.",
    "Open Calculator."
]

def run_tests():
    print("=" * 70)
    print("KYOMA PHASE 3 DEMO TEST RUNNER")
    print("=" * 70)
    
    llm = LLM()
    # Explicitly load Kyoma model as in server.py settings application
    llm.load_model_by_filename("Kyoma")
    print(f"Current LLM model: {llm.current_model_data.get('displayName') if llm.current_model_data else 'None'}")
    
    results = []
    
    for idx, phrase in enumerate(TEST_PHRASES, 1):
        print(f"\n[{idx}/15] Testing: '{phrase}'")
        t0 = time.perf_counter()
        
        # Call completion generator (same as /api/completion endpoint: get_completion(request.text, request.history, request.systemPrompt, request.screenshot))
        try:
            generator = llm.get_completion(phrase, history=[], system_prompt="", screenshot=False)
            chunks = []
            if generator:
                for chunk in generator:
                    chunks.append(chunk)
            spoken_text = "".join(chunks).strip()
            err = None
        except Exception as e:
            spoken_text = ""
            err = str(e)
            
        latency = time.perf_counter() - t0
        
        # Route detection
        if latency < 0.2 and not ("Error" in spoken_text):
            route = "fast_router"
        elif "Let me look that up" in spoken_text:
            route = "search_direct"
        else:
            route = "ollama"
            
        # Check leakage of paths, markdown, emojis
        path_leak = bool(re.search(r'[A-Za-z]:\\[^\s]+|\/[^\s]+\.[a-zA-Z0-9]+', spoken_text))
        markdown_leak = bool(re.search(r'[\*\_~`#>]|\[.*?\]\(.*?\)', spoken_text))
        emoji_leak = bool(re.search(r'[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]', spoken_text))
        
        has_leak = path_leak or markdown_leak or emoji_leak
        leak_details = []
        if path_leak: leak_details.append("path")
        if markdown_leak: leak_details.append("markdown")
        if emoji_leak: leak_details.append("emoji")
        
        res_record = {
            "index": idx,
            "phrase": phrase,
            "route": route,
            "latency_s": round(latency, 3),
            "spoken_text": spoken_text,
            "error": err,
            "leakage": leak_details,
            "leak_detected": has_leak
        }
        results.append(res_record)
        
        print(f"  Route: {route} | Latency: {latency:.3f}s")
        print(f"  Spoken: {spoken_text!r}")
        if has_leak:
            print(f"  LEAKAGE: {', '.join(leak_details)}")
        if err:
            print(f"  ERROR: {err}")
            
    # Save results to file
    out_path = os.path.join(REPO_ROOT, "_audit_tmp", "baseline_15_phrases.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
        
    print(f"\nResults saved to: {out_path}")
    return results

if __name__ == "__main__":
    run_tests()
