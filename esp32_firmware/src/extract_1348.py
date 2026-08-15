import json

transcript_path = r"C:\Users\harsh\.gemini\antigravity\brain\80cae36b-90e2-4973-8683-95ffe2521697\.system_generated\logs\transcript.jsonl"
output_path = r"c:\Users\harsh\Downloads\LocalAIVtuber2-master\LocalAIVtuber2-master\esp32_firmware\src\main.cpp.step1348"

found = False
with open(transcript_path, "r", encoding="utf-8") as f:
    for line in f:
        if '"step_index":1348,' in line:
            obj = json.loads(line)
            code = obj["tool_calls"][0]["args"]["CodeContent"]
            with open(output_path, "w", encoding="utf-8") as out:
                out.write(code)
            print("Successfully extracted step 1348 to main.cpp.step1348")
            found = True
            break

if not found:
    print("Step 1348 not found!")
