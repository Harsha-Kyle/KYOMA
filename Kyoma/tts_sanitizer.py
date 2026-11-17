import re
import os

def sanitize_for_tts(text: str) -> str:
    """
    Sanitize response text before sending to TTS engine.
    - Removes markdown formatting, bullet symbols, headings, and raw code blocks
    - Removes emojis and unsupported symbols
    - Never speaks raw file paths or internal traceback/error dumps
    - Converts tool outputs and raw dicts into natural confirmations
    - Preserves full sentences and thoughts without arbitrary word-count truncation
    """
    if not text:
        return ""
    s = str(text).strip()

    # If it's a dict or dict representation of a reminder
    if "repeat_interval" in s or ("'title':" in s and "'time':" in s) or ("'id':" in s and "'title':" in s):
        m_title = re.search(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", s)
        m_time = re.search(r"['\"]time['\"]\s*:\s*['\"]([^'\"]+)['\"]", s)
        if m_title:
            title_text = m_title.group(1).strip()
            if m_time:
                try:
                    from reminder_utils import _format_natural_time
                    time_nat = _format_natural_time(m_time.group(1).strip())
                    return f"Reminder set for {title_text} {time_nat}."
                except Exception:
                    pass
            return f"Reminder set for {title_text}."
        return "Reminder set successfully."

    # 1. Convert specific tool results to short natural confirmations
    s_lower = s.lower()
    if "screenshot" in s_lower and any(w in s_lower for w in ["saved", "taken", "captured"]):
        # Check if custom name was given
        m_name = re.search(r'screenshot saved as ([a-zA-Z0-9_\-\s]+?)(?:\.png|\.jpg|$|\.)', s, re.I)
        if m_name:
            clean_name = m_name.group(1).strip()
            return f"Screenshot saved as {clean_name}."
        m_file = re.search(r'screenshot saved[:\s]+[a-zA-Z]:\\[^\\]+\\([a-zA-Z0-9_\-\s]+?)_\d+.*\.png', s, re.I)
        if m_file:
            stem = m_file.group(1).strip()
            if stem and stem != "screenshot":
                return f"Screenshot saved as {stem}."
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
    s = re.sub(r'[A-Za-z]:\\[^\s,]+|\/[^\s,]+\.[a-zA-Z0-9]+', '', s)
    s = re.sub(r'Traceback \(most recent call last\):.*', 'An error occurred.', s, flags=re.DOTALL)
    s = re.sub(r'\{[^{}]*("ok"|"error"|"out")[^{}]*\}', '', s)

    # 3. Remove Markdown code blocks first
    s = re.sub(r'```.*?```', '', s, flags=re.DOTALL)
    s = re.sub(r'`(.*?)`', r'\1', s)

    # Remove Markdown formatting and headers
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)  # bold
    s = re.sub(r'\*(.*?)\*', r'\1', s)      # italics
    s = re.sub(r'__(.*?)__', r'\1', s)
    s = re.sub(r'_(.*?)_', r'\1', s)
    s = re.sub(r'#+\s*', '', s)             # headers
    s = re.sub(r'^\s*[\*\-\+]\s+', '', s, flags=re.MULTILINE) # bullets
    s = re.sub(r'^\s*\d+\.\s+', '', s, flags=re.MULTILINE)     # numbered lists
    s = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', s) # links
    s = re.sub(r'^\s*>\s+', '', s, flags=re.MULTILINE)        # blockquotes

    # 4. Remove emojis and non-standard symbols
    s = re.sub(r'[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]', '', s)
    s = re.sub(r'[❌✅🗓️🔔⏱️🛎️🚨🔁🧹🛑🗑️🎉🎂🖼️📸⚡😊⏭️⏮️]+', '', s)

    # 5. Clean extra whitespace and punctuation artifacts
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\s+([,\.\?!])', r'\1', s)

    return s
