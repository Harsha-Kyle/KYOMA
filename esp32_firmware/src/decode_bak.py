import ast
import os

def decode_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read().strip()
    
    # Try ast.literal_eval if it is wrapped in quotes
    if content.startswith('"') or content.startswith("'"):
        try:
            decoded = ast.literal_eval(content)
            with open(path, "w", encoding="utf-8") as f:
                f.write(decoded)
            print(f"ast.literal_eval decoded {os.path.basename(path)} successfully!")
            return
        except Exception as e:
            print(f"ast.literal_eval failed for {os.path.basename(path)}: {e}")
            
    # Alternative: replace escape sequences manually
    try:
        # If it's literally having '\n' characters in text
        decoded = content.strip('"').replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')
        with open(path, "w", encoding="utf-8") as f:
            f.write(decoded)
        print(f"Manual unescaped {os.path.basename(path)} successfully!")
    except Exception as e:
        print(f"Manual unescaped failed for {os.path.basename(path)}: {e}")

decode_file(r"c:\Users\harsh\Downloads\LocalAIVtuber2-master\LocalAIVtuber2-master\esp32_firmware\src\main.cpp.bak")
decode_file(r"c:\Users\harsh\Downloads\LocalAIVtuber2-master\LocalAIVtuber2-master\esp32_firmware\src\main.cpp.step1348")
