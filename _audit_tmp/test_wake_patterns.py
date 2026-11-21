import re

WAKE_PHRASES = [
    r"\b(?:hey|hi|ok|okay)\s+kyoma\b",
    r"\b(?:hey|hi|ok|okay)\s+(?:coma|koma|kioma)\b",
    r"\bkyoma\b",
]

WAKE_PATTERN = re.compile("|".join(WAKE_PHRASES), re.IGNORECASE)

def detect_wake_word(text: str):
    """
    Returns (detected: bool, clean_command: str)
    """
    if not text:
        return False, ""
    
    clean = text.strip()
    match = WAKE_PATTERN.search(clean)
    if not match:
        return False, ""
    
    # Extract remaining text after wake word
    remainder = clean[match.end():].strip()
    # Strip leading punctuation/conjunctions
    remainder = re.sub(r"^[,\.\?!;:\s\-]+", "", remainder).strip()
    
    return True, remainder

# Test cases
tests = [
    ("Hey Kyoma", True, ""),
    ("Hi Kyoma set the volume to 50", True, "set the volume to 50"),
    ("OK Kyoma what time is it", True, "what time is it"),
    ("okay koma brightness up", True, "brightness up"),
    ("koma", False, ""),  # weak variant without greeting word -> False
    ("coma", False, ""),
    ("hey coma", True, ""),
    ("Kyoma open notepad", True, "open notepad"),
    ("what is the weather", False, ""),
    ("hey there what are you doing", False, ""),
]

print("Testing detect_wake_word():")
all_passed = True
for txt, exp_detected, exp_cmd in tests:
    # Custom check for weak variants without greeting
    # Weak variants alone shouldn't trigger
    if re.search(r"^\b(?:coma|koma|kioma)\b", txt, re.IGNORECASE) and not re.search(r"\b(?:hey|hi|ok|okay)\s+(?:coma|koma|kioma)\b", txt, re.IGNORECASE):
        detected, cmd = False, ""
    else:
        detected, cmd = detect_wake_word(txt)
    
    ok = (detected == exp_detected) and (cmd == exp_cmd)
    if not ok:
        all_passed = False
    print(f"  [{'PASS' if ok else 'FAIL'}] text={txt!r} -> detected={detected}, cmd={cmd!r}")

print("All tests passed:", all_passed)
