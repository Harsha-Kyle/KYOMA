import json
with open('_audit_tmp/e2e_voice_latency_results.json', encoding='utf-8') as f:
    data = json.load(f)

print(f"{'Command':<42} | {'Path':<14} | {'Median (s)':<10} | {'Worst (s)':<10}")
print('-'*85)
for cmd, v in data.items():
    p = v['path']
    m = v['median_s']
    w = v['worst_s']
    print(f"{cmd:<42} | {p:<14} | {m:>10.3f} | {w:>10.3f}")
