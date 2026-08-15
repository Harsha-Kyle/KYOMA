import json
import os
import ast

transcript_path = r"C:\Users\harsh\.gemini\antigravity\brain\80cae36b-90e2-4973-8683-95ffe2521697\.system_generated\logs\transcript.jsonl"

def extract_step(target_step, out_name):
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            if f'"step_index":{target_step},' in line:
                try:
                    obj = json.loads(line)
                    for tc in obj.get("tool_calls", []):
                        args = tc.get("args", {})
                        code = args.get("CodeContent", "") or args.get("ReplacementContent", "")
                        if code:
                            if code.startswith('"'):
                                try:
                                    code = ast.literal_eval(code)
                                except:
                                    code = code.strip('"').replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
                            with open(out_name, "w", encoding="utf-8") as out:
                                out.write(code)
                            print(f"Extracted step {target_step} to {out_name} (length: {len(code)})")
                            return True
                except Exception as e:
                    print(f"Error for step {target_step}: {e}")
    print(f"Step {target_step} not found or failed.")
    return False

extract_step(1449, "step_1449.cpp")
extract_step(1473, "step_1473.cpp")
