"""
Live search test: checks search_web_evidence returns top 3, with expected fields.
Measures search latency.
"""
import sys, time
sys.path.insert(0, 'Kyoma')
sys.stdout.reconfigure(encoding='utf-8')
from search_evidence import search_web_evidence

queries = [
    "who is the president of the United States",
    "latest news about artificial intelligence",
    "what is Python programming language",
]

for q in queries:
    t0 = time.perf_counter()
    res = search_web_evidence(q, max_results=3)
    elapsed = time.perf_counter() - t0
    ok = res.get("ok")
    results = res.get("results", [])
    print(f"\nQuery: {q!r}")
    print(f"  OK={ok} | Results={len(results)} | Time={elapsed:.2f}s")
    for i, r in enumerate(results):
        print(f"  [{i+1}] {r.get('title','?')[:60]}")
        print(f"       Snippet: {str(r.get('snippet',''))[:80]}")
        print(f"       URL: {r.get('url','?')[:60]}")
        print(f"       Published: {r.get('published','?')}")
    assert ok, f"Search failed for: {q}"
    assert 1 <= len(results) <= 3, f"Expected 1-3 results, got {len(results)}"
    for r in results:
        assert 'title' in r and 'snippet' in r and 'url' in r and 'published' in r

print("\nAll search tests passed.")
