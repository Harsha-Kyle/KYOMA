import re

with open("Kyoma/fast_router.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update tools import to include play and pause
old_import = "from media_control    import play_pause, next_track, previous_track, startfrombegin_track"
new_import = "from media_control    import play_pause, play, pause, next_track, previous_track, startfrombegin_track"
assert old_import in content
content = content.replace(old_import, new_import)

old_tools_media = '''        # Media
        "play_pause":          play_pause,
        "next_track":          next_track,
        "previous_track":      previous_track,
        "startfrombegin_track":startfrombegin_track,'''

new_tools_media = '''        # Media
        "play_pause":          play_pause,
        "play":                play,
        "pause":               pause,
        "next_track":          next_track,
        "previous_track":      previous_track,
        "startfrombegin_track":startfrombegin_track,'''

assert old_tools_media in content
content = content.replace(old_tools_media, new_tools_media)

# 2. Update templates in _R
old_r_media = '''    "play_pause":      ["Done.",              "Toggled playback.",         "Played/paused."],
    "next_track":      ["Next track!",        "Skipping ahead.",           "Playing the next one."],
    "prev_track":      ["Previous track.",    "Going back one.",           "Playing the previous one."],
    "restart_track":   ["Starting over.",     "Back to the beginning.",    "Restarting from the top."],'''

new_r_media = '''    "play":            ["Playing.",           "Resumed.",                  "Playing."],
    "pause":           ["Paused.",            "Paused.",                   "Paused."],
    "play_pause":      ["Done.",              "Playback updated."],
    "next_track":      ["Next track.",        "Skipping ahead.",           "Playing the next one."],
    "prev_track":      ["Previous track.",    "Going back one.",           "Playing the previous one."],
    "restart_track":   ["Playing from the beginning.", "Back to the beginning.", "Restarting from the top."],'''

assert old_r_media in content
content = content.replace(old_r_media, new_r_media)

# 3. Update media regexes
old_media_re = '''# ── Media ─────────────────────────────────────────────────────────────────────
_RE_PLAY_PAUSE = re.compile(r"^(?:play|pause|toggle\\s+(?:play|media|music|playback)|play\\s*[/\\\\]\\s*pause|resume(?:\\s+(?:music|media|playback))?)$", _F)
_RE_NEXT       = re.compile(r"\\b(?:next\\s+(?:track|song|music)|skip(?:\\s+(?:this|track|song|music))?|forward(?:\\s+track)?)\\b", _F)
_RE_PREV       = re.compile(r"\\b(?:previous\\s+(?:track|song|music)|prev(?:\\s+(?:track|song|music))?|go\\s+back(?:\\s+(?:a\\s+)?(?:track|song))?|last\\s+(?:track|song))\\b", _F)
_RE_RESTART    = re.compile(r"\\b(?:restart(?:\\s+(?:track|song|music))?|replay(?:\\s+(?:this|track|song|music))?|from\\s+(?:the\\s+)?(?:beginning|start)|start\\s+(?:this\\s+)?over|beginning\\s+of\\s+(?:track|song))\\b", _F)'''

new_media_re = '''# ── Media ─────────────────────────────────────────────────────────────────────
_RE_PAUSE      = re.compile(r"^(?:pause(?:\\s+(?:it|the\\s+(?:video|song|music|track)|video|song|music|playback))?|stop(?:\\s+(?:the\\s+(?:video|song|music|track)|video|song|music|playback))?)$", _F)
_RE_PLAY       = re.compile(r"^(?:play(?:\\s+(?:it|the\\s+(?:video|song|music|track)|video|song|music|playback))?|resume(?:\\s+(?:it|the\\s+(?:video|song|music|track)|video|song|music|playback))?|continue(?:\\s+(?:the\\s+(?:video|song|music|track)|video|song|music|playback))?)$", _F)
_RE_PLAY_PAUSE = re.compile(r"^(?:toggle\\s+(?:play|media|music|playback)|play\\s*[/\\\\]\\s*pause)$", _F)
_RE_NEXT       = re.compile(r"\\b(?:next(?:\\s+(?:one|track|song|music))?|skip(?:\\s+(?:this|one|track|song|music))?|forward(?:\\s+track)?)\\b", _F)
_RE_PREV       = re.compile(r"\\b(?:previous(?:\\s+(?:one|track|song|music))?|prev(?:\\s+(?:one|track|song|music))?|go\\s+back(?:\\s+(?:to\\s+(?:the\\s+)?previous\\s+(?:track|song)|a\\s+(?:track|song)))?|last\\s+(?:track|song))\\b", _F)
_RE_RESTART    = re.compile(r"\\b(?:restart(?:\\s+(?:track|song|music))?|replay(?:\\s+(?:this|track|song|music))?|from\\s+(?:the\\s+)?(?:beginning|start)|start\\s+(?:this\\s+)?over|play\\s+(?:the\\s+(?:song|video|track)\\s+)?again|beginning\\s+of\\s+(?:track|song))\\b", _F)'''

assert old_media_re in content
content = content.replace(old_media_re, new_media_re)

# 4. Update reminder regexes to support "and 1 minute"
old_rem_re = '''_RE_REMIND_IN_SAYING = re.compile(
    r"\\b(?:set\\s+(?:a\\s+)?)?(?:reminder|remaining)\\s+in\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\\s+(?:saying|that\\s+says?)\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_ME_IN = re.compile(
    r"\\b(?:remind|remaining)\\s+(?:me\\s+)?in\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\\s+(?:to|that\\s+says?|saying)\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_FOR_TIME = re.compile(
    r"\\b(?:set\\s+(?:a\\s+)?)?(?:reminder|remaining)\\s+(?:for|at)\\s+(\\d{1,2}(?::\\d{2})?\\s*(?:AM|PM|am|pm))\\s+(?:saying|that\\s+says?|to)\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_IN_TO = re.compile(
    r"\\b(?:set\\s+(?:a\\s+)?)?(?:reminder|remaining)\\s+in\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\\s+to\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_TO_IN = re.compile(
    r"\\b(?:remind|remaining)\\s+(?:me\\s+)?to\\s+(.+?)\\s+in\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)[\\.\\?\\!]*$", _F)'''

new_rem_re = '''_RE_REMIND_IN_SAYING = re.compile(
    r"\\b(?:set\\s+(?:a\\s+)?)?(?:reminder|remaining)\\s+(?:in|and|after)\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\\s+(?:saying|that\\s+says?)\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_ME_IN = re.compile(
    r"\\b(?:remind|remaining)\\s+(?:me\\s+)?(?:in|and|after)\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\\s+(?:to|that\\s+says?|saying)\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_FOR_TIME = re.compile(
    r"\\b(?:set\\s+(?:a\\s+)?)?(?:reminder|remaining)\\s+(?:for|at)\\s+(\\d{1,2}(?::\\d{2})?\\s*(?:AM|PM|am|pm))\\s+(?:saying|that\\s+says?|to)\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_IN_TO = re.compile(
    r"\\b(?:set\\s+(?:a\\s+)?)?(?:reminder|remaining)\\s+(?:in|and|after)\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\\s+to\\s+(.+?)[\\.\\?\\!]*$", _F)
_RE_REMIND_TO_IN = re.compile(
    r"\\b(?:remind|remaining)\\s+(?:me\\s+)?to\\s+(.+?)\\s+(?:in|and|after)\\s+(\\d+|one|two|three|four|five|six|seven|eight|nine|ten)\\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)[\\.\\?\\!]*$", _F)'''

assert old_rem_re in content
content = content.replace(old_rem_re, new_rem_re)

# 5. Update media routing in _route()
old_media_route = '''    # ── MEDIA ─────────────────────────────────────────────────────────────────

    if _RE_PLAY_PAUSE.search(text):
        t["play_pause"]()
        return _say("play_pause"), True

    if _RE_NEXT.search(text):
        t["next_track"]()
        return _say("next_track"), True

    if _RE_PREV.search(text):
        t["previous_track"]()
        return _say("prev_track"), True

    if _RE_RESTART.search(text):
        t["startfrombegin_track"]()
        return _say("restart_track"), True'''

new_media_route = '''    # ── MEDIA ─────────────────────────────────────────────────────────────────

    if _RE_PAUSE.search(text):
        res = t["pause"]()
        return _say("pause") if res == "Paused." else res, True

    if _RE_PLAY.search(text):
        res = t["play"]()
        return _say("play") if res == "Playing." else res, True

    if _RE_PLAY_PAUSE.search(text):
        res = t["play_pause"]()
        return _say("play_pause"), True

    if _RE_NEXT.search(text):
        t["next_track"]()
        return _say("next_track"), True

    if _RE_PREV.search(text):
        t["previous_track"]()
        return _say("prev_track"), True

    if _RE_RESTART.search(text):
        t["startfrombegin_track"]()
        return _say("restart_track"), True'''

assert old_media_route in content
content = content.replace(old_media_route, new_media_route)

# 6. Update screenshot routing in _route() to NEVER leak path or emoji
old_ss_route = '''    if m := _RE_SCREENSHOT.search(text):
        name = m.group(1).strip() if m.group(1) else None
        res = t["take_screenshot_save"](name=name) if name else t["take_screenshot_save"]()
        r = _extract_result(res)
        return r, True'''

new_ss_route = '''    if m := _RE_SCREENSHOT.search(text):
        name = m.group(1).strip() if m.group(1) else None
        res = t["take_screenshot_save"](name=name) if name else t["take_screenshot_save"]()
        if name:
            return f"Screenshot saved as {name}.", True
        return "Screenshot saved.", True'''

assert old_ss_route in content
content = content.replace(old_ss_route, new_ss_route)

# 7. Update reminder routing in _route() to return the clean formatter output
old_rem_route = '''    # ── REMINDERS ─────────────────────────────────────────────────────────────
    if m := _RE_REMIND_IN_SAYING.search(text):
        raw_num = m.group(1).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(2).lower()
        action = m.group(3).strip()
        time_str = f"in {num} {unit}"
        t["add_reminder"](title=action, message=action, remind_time=time_str)
        return f"Reminder set. I'll remind you in {num} {unit} to {action}.", True

    if m := _RE_REMIND_ME_IN.search(text):
        raw_num = m.group(1).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(2).lower()
        action = m.group(3).strip()
        time_str = f"in {num} {unit}"
        t["add_reminder"](title=action, message=action, remind_time=time_str)
        return f"Reminder set. I'll remind you in {num} {unit} to {action}.", True

    if m := _RE_REMIND_FOR_TIME.search(text):
        time_val = m.group(1).strip()
        action = m.group(2).strip()
        t["add_reminder"](title=action, message=action, remind_time=time_val)
        return f"Reminder set for {time_val} to {action}.", True

    if m := _RE_REMIND_IN_TO.search(text):
        raw_num = m.group(1).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(2).lower()
        action = m.group(3).strip()
        time_str = f"in {num} {unit}"
        t["add_reminder"](title=action, message=action, remind_time=time_str)
        return f"Reminder set. I'll remind you in {num} {unit} to {action}.", True

    if m := _RE_REMIND_TO_IN.search(text):
        action = m.group(1).strip()
        raw_num = m.group(2).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(3).lower()
        time_str = f"in {num} {unit}"
        t["add_reminder"](title=action, message=action, remind_time=time_str)
        return f"Reminder set. I'll remind you in {num} {unit} to {action}.", True'''

new_rem_route = '''    # ── REMINDERS ─────────────────────────────────────────────────────────────
    if m := _RE_REMIND_IN_SAYING.search(text):
        raw_num = m.group(1).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(2).lower()
        action = m.group(3).strip()
        time_str = f"in {num} {unit}"
        res = t["add_reminder"](title=action, message=action, remind_time=time_str)
        return str(res), True

    if m := _RE_REMIND_ME_IN.search(text):
        raw_num = m.group(1).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(2).lower()
        action = m.group(3).strip()
        time_str = f"in {num} {unit}"
        res = t["add_reminder"](title=action, message=action, remind_time=time_str)
        return str(res), True

    if m := _RE_REMIND_FOR_TIME.search(text):
        time_val = m.group(1).strip()
        action = m.group(2).strip()
        res = t["add_reminder"](title=action, message=action, remind_time=time_val)
        return str(res), True

    if m := _RE_REMIND_IN_TO.search(text):
        raw_num = m.group(1).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(2).lower()
        action = m.group(3).strip()
        time_str = f"in {num} {unit}"
        res = t["add_reminder"](title=action, message=action, remind_time=time_str)
        return str(res), True

    if m := _RE_REMIND_TO_IN.search(text):
        action = m.group(1).strip()
        raw_num = m.group(2).lower()
        num = str(_WORD_TO_NUM.get(raw_num, raw_num))
        unit = m.group(3).lower()
        time_str = f"in {num} {unit}"
        res = t["add_reminder"](title=action, message=action, remind_time=time_str)
        return str(res), True'''

assert old_rem_route in content
content = content.replace(old_rem_route, new_rem_route)

# 8. Tighten "doing" so multi-sentence requests aren't captured
old_doing = '_RE_DOING        = re.compile(r"\\b(?:what\\s+are\\s+you\\s+doing|how\\s+are\\s+you(?:\\s+doing)?|how\'s\\s+it\\s+going)\\b", _F)'
new_doing = '_RE_DOING        = re.compile(r"^(?:what\\s+are\\s+you\\s+doing|how\\s+are\\s+you(?:\\s+doing)?|how\'s\\s+it\\s+going)[\\!\\.\\?\\s]*$", _F)'
assert old_doing in content
content = content.replace(old_doing, new_doing)

with open("Kyoma/fast_router.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Kyoma/fast_router.py updated successfully!")
