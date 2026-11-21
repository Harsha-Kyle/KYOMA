import re
import os

def sanitize_for_tts(text: str) -> str:
    """
    Sanitize response text before sending to TTS engine.
    - Cleans Markdown formatting, bullet symbols, headings, and code blocks
    - Converts colons/semicolons into natural speech pauses (preserving times like 10:30 AM)
    - Removes punctuation-only noise and unsupported symbols
    - Preserves meaningful spoken text, numbers, and normal sentence punctuation
    - Returns empty string if no spoken words or numbers exist
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
        m_name = re.search(r"screenshot saved as ([a-zA-Z0-9_\-\s]+?)(?:\.png|\.jpg|$|\.)", s, re.I)
        if m_name:
            clean_name = m_name.group(1).strip()
            return f"Screenshot saved as {clean_name}."
        m_file = re.search(r"screenshot saved[:\s]+[a-zA-Z]:\\[^\\]+\\([a-zA-Z0-9_\-\s]+?)_\d+.*\.png", s, re.I)
        if m_file:
            stem = m_file.group(1).strip()
            if stem and stem != "screenshot":
                return f"Screenshot saved as {stem}."
        return "Screenshot saved successfully."

    if "opened" in s_lower:
        m = re.search(r"([a-zA-Z0-9_-]+)\.exe", s, re.I)
        if m:
            return f"Opening {m.group(1).title()}."
        m2 = re.search(r"opened\s+([a-zA-Z0-9_-]+)", s, re.I)
        if m2:
            return f"Opening {m2.group(1).title()}."
        return "Application opened."

    if "reminder" in s_lower:
        m_dict = re.search(r"['\"]title['\"]\s*:\s*['\"]([^'\"]+)['\"]", s)
        if m_dict:
            return f"Reminder set for {m_dict.group(1).strip()}."
        m_set = re.search(r"reminder\s+set.*?[:\s]+['\"]?([^'\"]+?)['\"]?\s+at\s+", s, re.I)
        if m_set:
            return f"Reminder set for {m_set.group(1).strip()}."

    # 2. Never speak raw local file paths or internal error details
    s = re.sub(r"\b[A-Za-z]:\\[^\s,]+|\/[^\s,]+\.[a-zA-Z0-9]+", "", s)
    s = re.sub(r"Traceback \(most recent call last\):.*", "An error occurred.", s, flags=re.DOTALL)
    s = re.sub(r"\{[^{}]*['\"](?:ok|error|out)['\"][^{}]*\}", "", s)

    # 3. Remove Markdown code blocks & inline code
    s = re.sub(r"```.*?```", "", s, flags=re.DOTALL)
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # 4. Snake_case into separate words FIRST
    s = re.sub(r"(?<=\w)_(?=\w)", " ", s)

    # 5. Remove Markdown bold and italics
    s = re.sub(r"\*\*(.*?)\*\*", r"\1", s)
    s = re.sub(r"\*(.*?)\*", r"\1", s)
    s = re.sub(r"__(.*?)__", r"\1", s)
    s = re.sub(r"_(.*?)_", r"\1", s)
    s = re.sub(r"#+\s*", "", s)

    # 6. Lists: turn items into natural sentences ending with periods
    def _clean_list_item(m):
        item = m.group(1).strip()
        if item and not item.endswith((".", "!", "?", ",", ";")):
            return item + ". "
        return item + " "
    s = re.sub(r"^\s*[\*\-\+]\s+(.*)$", _clean_list_item, s, flags=re.MULTILINE)
    s = re.sub(r"^\s*\d+\.\s+(.*)$", _clean_list_item, s, flags=re.MULTILINE)

    s = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", s)
    s = re.sub(r"^\s*>\s+", "", s, flags=re.MULTILINE)

    # 7. Colons: preserve time formats (e.g. 10:30 AM, 12:45)
    s = re.sub(r"(?<=\d):(?=\d{2}\b)", "___TIME_COLON___", s)
    # Convert all other colons into a natural pause
    s = re.sub(r":\s*", ", ", s)
    s = s.replace("___TIME_COLON___", ":")

    # 8. Semicolons into natural pauses
    s = re.sub(r";\s*", ", ", s)

    # 9. Strip remaining symbols
    s = re.sub(r"[*~`#><|^\\{}[\]()]", "", s)

    # 10. Remove emojis
    s = re.sub(r"[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf]", "", s)
    s = re.sub(r"[❌✅🗓️🔔⏱️🛎️🚨🔁🧹🛑🗑️🎉🎂🖼️📸⚡😊⏭️⏮️]+", "", s)

    # 11. Clean extra commas and whitespace
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r"\s+([,.\?!])", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"^[\s,]+", "", s)

    # 12. Skip chunks containing no actual words or numbers
    if not re.search(r"[a-zA-Z0-9]", s):
        return ""

    return s
