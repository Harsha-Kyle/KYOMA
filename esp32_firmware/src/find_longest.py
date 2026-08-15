import json
import os

transcript_path = r"C:\Users\harsh\.gemini\antigravity\brain\80cae36b-90e2-4973-8683-95ffe2521697\.system_generated\logs\transcript.jsonl"

longest_code = ""
longest_step = -1

with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if "write_to_file" in line:
            try:
                obj = json.loads(line)
                step = obj.get("step_index", "unknown")
                for tc in obj.get("tool_calls", []):
                    args = tc.get("args", {})
                    target = args.get("TargetFile", "")
                    if "main.cpp" in target:
                        code = args.get("CodeContent", "")
                        if len(code) > len(longest_code):
                            longest_code = code
                            longest_step = step
            except:
                pass

print(f"Longest step: {longest_step}, length: {len(longest_code)}")
if longest_code:
    # Clean the code (some might be escaped, some might be direct)
    if longest_code.startswith('"'):
        try:
            import ast
            longest_code = ast.literal_eval(longest_code)
        except:
            longest_code = longest_code.strip('"').replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
            
    with open("longest_main.cpp", "w", encoding="utf-8") as out:
        out.write(longest_code)
    print("Saved longest main.cpp to longest_main.cpp")
