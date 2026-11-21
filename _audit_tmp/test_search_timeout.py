import sys
import time
from unittest.mock import patch
sys.path.insert(0, 'Kyoma')
from ollama_workflow import execute_ollama_workflow
from memory_manager import MemoryManager

mem = MemoryManager(max_history=3)
queries = ['current prime minister of India', 'who is Sam Altman', 'what happened with OpenAI']

print("=== TESTING OFFLINE SEARCH (5 runs per query via simulated offline check) ===")
# Patch _check_connectivity to return False
with patch('ollama_workflow._check_connectivity', return_value=False):
    for q in queries:
        latencies = []
        texts = []
        for i in range(5):
            t0 = time.perf_counter()
            res = execute_ollama_workflow(q, 'gemma4:e2b', mem, [])
            dt = time.perf_counter() - t0
            latencies.append(dt)
            texts.append(res.get('text'))
        avg_l = sum(latencies)/len(latencies)
        print(f"Query: {q!r} -> Offline fast-fail: 5/5, Avg latency: {avg_l*1000:.1f}ms, Spoken: {texts[0]!r}")

print("\n=== TESTING FORCED TIMEOUT SCENARIOS (5 runs) ===")
# Force search_web_evidence to hang or exceed 15s timeout
def slow_search(*args, **kwargs):
    time.sleep(20.0)
    return {"ok": False, "results": []}

with patch('ollama_workflow._check_connectivity', return_value=True), \
     patch('ollama_workflow.search_web_evidence', side_effect=slow_search):
    for i in range(5):
        t0 = time.perf_counter()
        res = execute_ollama_workflow("who is Sam Altman", 'gemma4:e2b', mem, [])
        dt = time.perf_counter() - t0
        print(f"Timeout Run {i+1}: wall={dt:.2f}s, Handled safely: {res.get('ok')}, Fallback spoken: {res.get('text')!r}")
