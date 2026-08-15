import json
import os

transcript_path = r"C:\Users\harsh\.gemini\antigravity\brain\80cae36b-90e2-4973-8683-95ffe2521697\.system_generated\logs\transcript.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if "void drawEyes" in line or "drawEyes()" in line:
            try:
                obj = json.loads(line)
                step = obj.get("step_index", "unknown")
                for tc in obj.get("tool_calls", []):
                    args = tc.get("args", {})
                    content = args.get("CodeContent", "") or args.get("ReplacementContent", "")
                    if "drawEyes" in content and len(content) > 300 and "truncated" not in content:
                        print(f"Step {step}: found drawEyes (len: {len(content)})")
                        print(content[:500])
                        print("...")
                        print(content[-500:])
                        print("="*60)
            except Exception as e:
                pass
