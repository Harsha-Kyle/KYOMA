import json
import re

transcript_path = r"C:\Users\harsh\.gemini\antigravity\brain\80cae36b-90e2-4973-8683-95ffe2521697\.system_generated\logs\transcript.jsonl"

with open(transcript_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if "write_to_file" in line or "replace_file_content" in line:
            # Check if it mentions main.cpp
            if "main.cpp" in line:
                try:
                    obj = json.loads(line)
                    step = obj.get("step_index", "unknown")
                    source = obj.get("source", "unknown")
                    t_type = obj.get("type", "unknown")
                    
                    # Look for tool calls in model response or system response
                    t_calls = obj.get("tool_calls", [])
                    for tc in t_calls:
                        args = tc.get("args", {})
                        target = args.get("TargetFile", "")
                        if "main.cpp" in target:
                            print(f"Line {i+1}: Step {step}, Type {t_type}, Source {source}, Tool {tc['name']}")
                            if tc['name'] == 'write_to_file':
                                content = args.get("CodeContent", "")
                                print(f"  Length of CodeContent: {len(content)}")
                            elif tc['name'] == 'replace_file_content':
                                rep = args.get("ReplacementContent", "")
                                tgt = args.get("TargetContent", "")
                                print(f"  Replace target length: {len(tgt)} with length: {len(rep)}")
                except Exception as e:
                    print(f"Error parsing line {i+1}: {e}")
