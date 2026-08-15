import os

search_dir = r"c:\Users\harsh\Downloads\LocalAIVtuber2-master\LocalAIVtuber2-master\backend"

found = False
for root, dirs, files in os.walk(search_dir):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "process_esp32_audio" in content:
                    print(f"Found in {path}:")
                    idx = content.find("def process_esp32_audio")
                    print(content[idx:idx+1200])
                    found = True
            except Exception as e:
                pass
if not found:
    print("Not found anywhere in backend!")
