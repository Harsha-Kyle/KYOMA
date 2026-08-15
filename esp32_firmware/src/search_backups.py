import os

search_dir = r"c:\Users\harsh\Downloads\LocalAIVtuber2-master"
keywords = ["u8g2", "playTone", "currentState", "webSocketEvent"]

found_files = []
for root, dirs, files in os.walk(search_dir):
    for file in files:
        if file.endswith((".cpp", ".h", ".bak", ".old", ".tmp", ".ino")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = [kw for kw in keywords if kw in content]
                    if matches:
                        found_files.append((path, len(content), matches))
            except Exception as e:
                pass

print(f"Found {len(found_files)} matching files:")
for path, size, matches in found_files:
    print(f"File: {path} ({size} bytes) - Matches: {matches}")
