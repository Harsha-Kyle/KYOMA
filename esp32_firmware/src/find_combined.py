import json
import os

transcript_path = r"C:\Users\harsh\.gemini\antigravity\brain\80cae36b-90e2-4973-8683-95ffe2521697\.system_generated\logs\transcript.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if "WiFi.begin" in line and "main.cpp" in line:
            try:
                obj = json.loads(line)
                step = obj.get("step_index", "unknown")
                for tc in obj.get("tool_calls", []):
                    args = tc.get("args", {})
                    target = args.get("TargetFile", "")
                    if "main.cpp" in target:
                        content = args.get("CodeContent", "") or args.get("ReplacementContent", "")
                        if "WiFi.begin" in content:
                            print(f"Step {step}: found combined code (len: {len(content)})")
                            print(content[:800])
                            print("...")
                            print(content[-800:])
                            print("="*60)
            except Exception as e:
                pass
