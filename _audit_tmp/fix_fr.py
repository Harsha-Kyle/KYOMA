with open('Kyoma/fast_router.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix the accidental replace on line 741
text = text.replace('check_demo_mode_refusal("close_application","add_reminder","list_active_reminders", {"name": name})', 'check_demo_mode_refusal("close_application", {"name": name})')

# Fix 'open' bare word pattern:
# 'open' by itself should return "What would you like me to open?" OR not match if it's meant to fall through.
# In _test(): ('open', None) expects it NOT to match or fall through.
# Let's check _RE_OPEN_BARE and _RE_OPEN_APP.
# If 'open' is given without an app name, _RE_OPEN_BARE matched 'open' and returned "What would you like me to open?".
# If the test expects it not to match, let's see.

with open('Kyoma/fast_router.py', 'w', encoding='utf-8') as f:
    f.write(text)
