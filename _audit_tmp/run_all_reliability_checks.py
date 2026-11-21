import sys
sys.path.insert(0, 'LocalAIVtuber2-master')
sys.path.insert(0, 'LocalAIVtuber2-master/Kyoma')
import fast_router
from tts_sanitizer import sanitize_for_tts
import reminder_utils

print('1. Testing TTS sanitizer:')
sample = (
    "**Information Retrieval:**\n"
    "- `web_search`: Search the web\n"
    "- `get_battery`: Check battery level\n"
    "- `take_screenshot_save`: Capture screen\n"
    "- `set_volume`: Set audio volume"
)
cleaned = sanitize_for_tts(sample)
print('  Cleaned text:\n  ', cleaned)
assert '`' not in cleaned, "Backticks remain"
assert '*' not in cleaned, "Asterisks remain"
assert 'take_screenshot_save' not in cleaned, "Raw snake_case remains"
assert 'web_search' not in cleaned, "Raw tool identifier remains"
assert 'take screenshot' in cleaned, "Tool conversion missing"
assert 'web search' in cleaned, "Tool conversion missing"
print('  [PASS] TTS Sanitizer verified!')

print('2. Testing FastRouter:')
test_phrases = [
    ('media pause', True),
    ('media pass', True),
    ('stop the video', True),
    ('stop youtube', True),
    ('resume', True),
    ('continue', True),
    ('mute', True),
    ('set volume to 40', True),
]
for p, expected in test_phrases:
    ans, matched = fast_router.route(p)
    assert matched == expected, f'Failed for {p}: got {matched}'
    print(f'  [PASS] {p!r} -> {ans!r}')

print('3. Testing Reminders Voice Function:')
assert reminder_utils._is_reminder_voice_enabled() == True
print('  [PASS] Reminder voice enabled verified!')

print('\nALL AUTOMATED CHECKS PASSED!')
