import re

def sanitize_for_tts(text: str) -> str:
    """
    Sanitize response text before sending to TTS engine.
    - Removes markdown formatting, bullet symbols, and raw code blocks
    - Removes emojis and unsupported symbols
    - Never speaks raw file paths or internal traceback/error dumps
    - Converts tool outputs into natural, short confirmations
    - Limits spoken response length to ~25-30 words
    """
    if not text:
        return ""
    s = str(text).strip()

    # If it's a dict or dict representation of a reminder
    if "repeat_interval" in s or ("'title':" in s and "'time':" in s):
        m_title = re.search(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", s)
        if m_title:
            return f"Reminder set for {m_title.group(1).strip()}."
        return "Reminder set successfully."

    # 1. Convert specific tool results to short natural confirmations
    s_lower = s.lower()
    if "screenshot" in s_lower and any(w in s_lower for w in ["saved", "taken", "captured"]):
        return "Screenshot saved successfully."
    
    if "opened" in s_lower:
        m = re.search(r'([a-zA-Z0-9_-]+)\.exe', s, re.I)
        if m:
            return f"Opening {m.group(1).title()}."
        m2 = re.search(r'opened\s+([a-zA-Z0-9_-]+)', s, re.I)
        if m2:
            return f"Opening {m2.group(1).title()}."
        return "Application opened."

    if "reminder" in s_lower:
        m_dict = re.search(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", s)
        if m_dict:
            return f"Reminder set for {m_dict.group(1).strip()}."
        m_set = re.search(r'reminder\s+set.*?:\s*[\'"]?([^\'"]+?)[\'"]?\s+at\s+', s, re.I)
        if m_set:
            return f"Reminder set for {m_set.group(1).strip()}."

    # 2. Never speak raw local file paths or internal error details
    s = re.sub(r'[A-Za-z]:\\[^\s,]+|\/[^\s,]+\.[a-zA-Z0-9]+', 'file', s)
    s = re.sub(r'Traceback \(most recent call last\):.*', 'An error occurred.', s, flags=re.DOTALL)

    # 3. Remove Markdown formatting and bullet symbols
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)  # bold
    s = re.sub(r'\*(.*?)\*', r'\1', s)      # italics
    s = re.sub(r'__(.*?)__', r'\1', s)
    s = re.sub(r'_(.*?)_', r'\1', s)
    s = re.sub(r'`(.*?)`', r'\1', s)        # inline code
    s = re.sub(r'#+\s*', '', s)             # headers
    s = re.sub(r'^\s*[\*\-\+]\s+', '', s, flags=re.MULTILINE) # bullets
    s = re.sub(r'^\s*\d+\.\s+', '', s, flags=re.MULTILINE)     # numbered lists
    s = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', s) # links

    # 4. Remove emojis and symbols
    s = re.sub(r'[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]', '', s)
    s = re.sub(r'[❌✅🗓️🔔⏱️🛎️🚨🔁🧹🛑🗑️🎉🎂🖼️📸⚡😊]+', '', s)

    # 5. Clean extra whitespace
    s = re.sub(r'\s+', ' ', s).strip()

    # 6. Length limiting (~25 words for routine spoken confirmations)
    words = s.split()
    if len(words) > 35:
        sentences = re.split(r'(?<=[.!?])\s+', s)
        if len(sentences) > 1 and len(sentences[0].split()) <= 25:
            s = sentences[0]
            if len((s + ' ' + sentences[1]).split()) <= 32:
                s = s + ' ' + sentences[1]
        elif len(words) > 30:
            s = ' '.join(words[:25]) + '.'

    return s
