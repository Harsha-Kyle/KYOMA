with open('Kyoma/fast_router.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Fix _is_plausible_name
old_plaus = '''def _is_plausible_name(name: str) -> bool:
    """Reject match groups that are obviously not an app/site name."""
    if not name or len(name) > 50:
        return False
    # Reject lone function words
    noise = {"it", "that", "this", "the", "a", "an", "them", "me", "us"}
    if name.lower() in noise:
        return False
    return True'''

new_plaus = '''def _is_plausible_name(name: str) -> bool:
    """Reject match groups that are obviously not an app/site name."""
    if not name or len(name) > 40:
        return False
    n = name.lower().strip()
    # Reject lone function words
    noise = {"it", "that", "this", "the", "a", "an", "them", "me", "us", "something", "anything"}
    if n in noise:
        return False
    # Reject multi-sentence or conjunction-ridden strings
    if re.search(r"\\b(?:and|then|also|with|about|tell|story|joke|help)\\b", n):
        return False
    return True'''

assert old_plaus in text
text = text.replace(old_plaus, new_plaus)

# 2. Fix _RE_OPEN_APP and _RE_OPEN_SITE to be anchored and reject bare open
old_open_app = '_RE_OPEN_APP   = re.compile(rf"\\b{_OPEN_WORDS}\\s+(?:the\\s+)?(.+?){_APP_SUFFIX}", _F)'
new_open_app = '_RE_OPEN_APP   = re.compile(rf"^{_OPEN_WORDS}\\s+(?:the\\s+)?([a-zA-Z0-9_\\-\\s]+?){_APP_SUFFIX}$", _F)'
assert old_open_app in text
text = text.replace(old_open_app, new_open_app)

# 3. Bare open shouldn't hijack - fall through to LLM
old_open_bare = '''    if _RE_OPEN_BARE.match(text):
        return "What would you like me to open?", True'''
new_open_bare = '''    if _RE_OPEN_BARE.match(text):
        return None, False'''
assert old_open_bare in text
text = text.replace(old_open_bare, new_open_bare)

with open('Kyoma/fast_router.py', 'w', encoding='utf-8') as f:
    f.write(text)

print("Updated fast_router plausibility & open-app regexes.")
