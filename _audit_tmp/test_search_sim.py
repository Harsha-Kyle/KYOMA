import sys
import time
sys.path.insert(0, 'Kyoma')
from search_evidence import search_web_evidence

queries = ['current prime minister of India', 'who is Sam Altman', 'what happened with OpenAI']
print("=== TESTING ONLINE SEARCH (5 runs per query) ===")
for q in queries:
    latencies = []
    successes = 0
    res = {}
    for i in range(5):
        t0 = time.perf_counter()
        res = search_web_evidence(q, max_results=3)
        dt = time.perf_counter() - t0
        latencies.append(dt)
        if res.get('ok') and len(res.get('results', [])) > 0:
            successes += 1
    avg_l = sum(latencies)/len(latencies)
    count = len(res.get('results', []))
    print(f"Query: {q!r} -> Success: {successes}/5, Avg latency: {avg_l:.2f}s, Results: {count}")
