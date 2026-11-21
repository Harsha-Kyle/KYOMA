import time, json, statistics, ollama

phrases = [
    'Hello, who are you?',
    'What can you do for me?',
    'Tell me a short fun fact.',
    'What is your name?',
    'How does your AI work?',
    'Give me a motivational quote.',
    'Say hello to the college audience.',
    'What time is best for studying?',
    'Explain your physical companion hardware.',
    'Thank you for your help.'
]

print('=== BENCHMARKING 10 CHAT PHRASES WITH CURRENT SETTINGS ===')
current_results = []
for p in phrases:
    t0 = time.perf_counter()
    resp = ollama.chat(
        model='gemma4:e2b',
        messages=[{'role': 'user', 'content': p}],
        keep_alive='1h',
        options={'temperature': 0.2}
    )
    t_wall = time.perf_counter() - t0
    c_tot = resp.get('total_duration', 0) / 1e9
    c_load = resp.get('load_duration', 0) / 1e9
    c_eval = resp.get('eval_duration', 0) / 1e9
    c_eval_tok = resp.get('eval_count', 0)
    has_think = bool(resp.get('message', {}).get('thinking'))
    current_results.append({
        'phrase': p,
        'wall': t_wall,
        'total': c_tot,
        'load': c_load,
        'eval': c_eval,
        'tokens': c_eval_tok,
        'think': has_think,
        'text': resp.get('message', {}).get('content', '')
    })
    print(f'"{p[:30]}...": wall={t_wall:.2f}s | load={c_load:.2f}s | eval={c_eval:.2f}s | tok={c_eval_tok} | think={has_think}')

print('\n=== BENCHMARKING 10 CHAT PHRASES WITH OPTIMIZED SETTINGS (think=False, num_predict=80, temp=0.2) ===')
opt_results = []
for p in phrases:
    t0 = time.perf_counter()
    resp = ollama.chat(
        model='gemma4:e2b',
        messages=[{'role': 'user', 'content': p}],
        keep_alive='1h',
        think=False,
        options={'temperature': 0.2, 'num_predict': 80}
    )
    t_wall = time.perf_counter() - t0
    c_tot = resp.get('total_duration', 0) / 1e9
    c_load = resp.get('load_duration', 0) / 1e9
    c_eval = resp.get('eval_duration', 0) / 1e9
    c_eval_tok = resp.get('eval_count', 0)
    has_think = bool(resp.get('message', {}).get('thinking'))
    opt_results.append({
        'phrase': p,
        'wall': t_wall,
        'total': c_tot,
        'load': c_load,
        'eval': c_eval,
        'tokens': c_eval_tok,
        'think': has_think,
        'text': resp.get('message', {}).get('content', '')
    })
    print(f'"{p[:30]}...": wall={t_wall:.2f}s | load={c_load:.2f}s | eval={c_eval:.2f}s | tok={c_eval_tok} | think={has_think}')

cur_walls = [r['wall'] for r in current_results]
opt_walls = [r['wall'] for r in opt_results]
print(f'\nCURRENT: median={statistics.median(cur_walls):.2f}s, mean={statistics.mean(cur_walls):.2f}s, max={max(cur_walls):.2f}s')
print(f'OPTIMIZED: median={statistics.median(opt_walls):.2f}s, mean={statistics.mean(opt_walls):.2f}s, max={max(opt_walls):.2f}s')

with open('_audit_tmp/ollama_optimization_benchmark.json', 'w', encoding='utf-8') as f:
    json.dump({'current': current_results, 'optimized': opt_results}, f, indent=2)
