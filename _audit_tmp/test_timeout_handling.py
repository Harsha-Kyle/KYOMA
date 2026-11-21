import sys
import time
import threading
import concurrent.futures
from unittest.mock import patch
sys.path.insert(0, 'Kyoma')
from ollama_workflow import execute_ollama_workflow
from memory_manager import MemoryManager

mem = MemoryManager(max_history=3)

print("=== TESTING FORCED TIMEOUT SCENARIOS (5 runs with simulated timeout) ===")
threads_before = threading.active_count()
for i in range(5):
    t0 = time.perf_counter()
    with patch('ollama_workflow._check_connectivity', return_value=True), \
         patch('concurrent.futures.Future.result', side_effect=concurrent.futures.TimeoutError('Search timed out after 15s')):
        res = execute_ollama_workflow("who is Sam Altman", 'gemma4:e2b', mem, [])
    dt = time.perf_counter() - t0
    txt = res.get('text')
    ok = res.get('ok')
    print(f"Run {i+1}: wall={dt:.3f}s | handled={ok} | text={txt!r}")

threads_after = threading.active_count()
print(f"Thread count check: before={threads_before}, after={threads_after} (accumulated={threads_after - threads_before})")
