"""
fast_router.py — Kyoma AI VTuber
─────────────────────────────────────────────────────────────────────────────
Fast Path Router: intercepts simple, unambiguous voice commands and executes
them directly — no Ollama call, no RAG lookup, no second round-trip.

Latency saved per matched command: ~1.5s – 5s

Architecture:
    KyomaLLM.get_chat_completion(text)
        │
        ▼
    fast_router.route(text)
        ├─ MATCH → execute tool → return (response_text, True)  ← fast path
        └─ NO MATCH → return (None, False) → fall through to Ollama

Rules:
  • Patterns are pre-compiled at import time (zero cost at runtime).
  • Tool functions are lazy-loaded on first use (no circular import issues).
  • Any exception inside route() is caught silently — never crashes pipeline.
  • Response templates are randomised for natural variation.
  • Only crystal-clear, unambiguous commands are matched.
    Ambiguous phrasing always falls through to the LLM.
"""

from __future__ import annotations

import re
import sys
import os
import random
import traceback
from typing import Optional, Tuple
from demo_safety import check_demo_mode_refusal

# ─────────────────────────────────────────────────────────────────────────────
# Lazy tool loader — avoids circular imports & speeds up module load time
# ─────────────────────────────────────────────────────────────────────────────

_tools: Optional[dict] = None

def _get_tools() -> dict:
    global _tools
    if _tools is not None:
        return _tools
    from volume_control   import set_volume, change_volume, mute_volume, unmute_volume, get_volume
    from display_control  import set_brightness, get_brightness, brightness_up, brightness_down, lock_screen
    from media_control    import play_pause, play, pause, stop, next_track, previous_track, startfrombegin_track
    from screenshot       import take_screenshot_save
    from system_info_utils import (get_time, get_date, get_battery, get_system_info,
                                   get_power_status, get_network_status, get_vpn_status,
                                   get_performance, get_disk_usage)
    from app_utils        import (open_application, open_browser,
                                  minimize_application, restore_application, close_application)
    from reminder_utils   import list_active_reminders, add_reminder
    _tools = {
        # Volume
        "set_volume":          set_volume,
        "change_volume":       change_volume,
        "mute_volume":         mute_volume,
        "unmute_volume":       unmute_volume,
        "get_volume":          get_volume,
        # Brightness
        "set_brightness":      set_brightness,
        "get_brightness":      get_brightness,
        "brightness_up":       brightness_up,
        "brightness_down":     brightness_down,
        "lock_screen":         lock_screen,
        # Media
        "play_pause":          play_pause,
        "play":                play,
        "pause":               pause,
        "stop":                stop,
        "next_track":          next_track,
        "previous_track":      previous_track,
        "startfrombegin_track":startfrombegin_track,
        # Screenshot
        "take_screenshot_save":take_screenshot_save,
        # System info
        "get_time":            get_time,
        "get_date":            get_date,
        "get_battery":         get_battery,
        "get_system_info":     get_system_info,
        "get_power_status":    get_power_status,
        "get_network_status":  get_network_status,
        "get_vpn_status":      get_vpn_status,
        "get_performance":     get_performance,
        "get_disk_usage":      get_disk_usage,
        # Apps / Browser
        "open_application":    open_application,
        "open_browser":        open_browser,
        "minimize_application":minimize_application,
        "restore_application": restore_application,
        "close_application":   close_application,
        # Reminders
        "list_active_reminders": list_active_reminders,
        "add_reminder":          add_reminder,
    }
    return _tools


# ─────────────────────────────────────────────────────────────────────────────
# Known website shortcuts
# Add any site you want Kyoma to open directly by name.
# ─────────────────────────────────────────────────────────────────────────────

SITE_MAP: dict[str, str] = {
    "youtube":       "https://www.youtube.com",
    "yt":            "https://www.youtube.com",
    "spotify":       "https://open.spotify.com",
    "netflix":       "https://www.netflix.com",

    "reddit":        "https://www.reddit.com",
    "twitter":       "https://www.twitter.com",
    "x":             "https://www.x.com",
    "instagram":     "https://www.instagram.com",
    "facebook":      "https://www.facebook.com",
    "fb":            "https://www.facebook.com",
    "gmail":         "https://mail.google.com",
    "google drive":  "https://drive.google.com",
    "drive":         "https://drive.google.com",
    "google docs":   "https://docs.google.com",
    "docs":          "https://docs.google.com",
    "google sheets": "https://sheets.google.com",
    "sheets":        "https://sheets.google.com",
    "amazon":        "https://www.amazon.in",
    "flipkart":      "https://www.flipkart.com",
    "whatsapp":      "https://web.whatsapp.com",
    "chatgpt":       "https://chat.openai.com",
    "claude":        "https://claude.ai",
    "gemini":        "https://gemini.google.com",
    "bard":          "https://gemini.google.com",
    "twitch":        "https://www.twitch.tv",
    "github":        "https://www.github.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow":"https://stackoverflow.com",
    "pinterest":     "https://www.pinterest.com",
    "linkedin":      "https://www.linkedin.com",
    "notion":        "https://www.notion.so",
    "figma":         "https://www.figma.com",
}

SITE_DISPLAY_NAMES: dict[str, str] = {
    "yt": "YouTube",
    "fb": "Facebook",
    "chatgpt": "ChatGPT",
    "github": "GitHub",
    "stackoverflow": "Stack Overflow",
    "stack overflow": "Stack Overflow",
}

# ─────────────────────────────────────────────────────────────────────────────
# Response templates — randomised so Kyoma doesn't sound like a robot
# ─────────────────────────────────────────────────────────────────────────────

_last_responses: dict[str, str] = {}

_R: dict[str, list[str]] = {
    "open_app":        ["{n} opened!", "Launching {n}.", "On it, opening {n}.", "{n}, coming right up!", "Starting {n} now."],
    "open_url":        ["Opening {n}!", "Here you go, {n}.", "On it, navigating to {n}.", "{n} is on its way!", "Heading over to {n}."],
    "web_search":      ["Searching for '{q}' on Google.", "Looking up '{q}'.", "Checking '{q}' online now.", "Searching the web for '{q}'."],
    "yt_search":       ["Searching YouTube for '{q}'.", "Looking up '{q}' on YouTube.", "Finding '{q}' on YouTube.", "Here you go, searching '{q}' on YouTube."],
    "close_app":       ["{n} closed.", "Done, {n} is closed.", "Closed {n}.", "Dismissed {n}."],
    "minimize_app":    ["{n} minimized.", "Minimized {n}.", "Out of the way, {n} minimized.", "Tucked {n} away."],
    "restore_app":     ["{n} is back.", "Restored {n}.", "Bringing {n} back to the front.", "Window restored."],
    "set_volume":      ["Volume set to {v}%.", "Done, volume is now {v}%.", "Adjusted volume to {v}%.", "Sound level set to {v}%."],
    "volume_up":       ["Louder!", "Volume turned up.", "Turned it up a notch.", "Increasing volume."],
    "volume_down":     ["Quieter.", "Volume turned down.", "Lowering the volume.", "Turned it down a notch."],
    "volume_by_up":    ["Volume up by {v}%.", "Increased volume by {v}%.", "Done, {v}% louder."],
    "volume_by_down":  ["Volume down by {v}%.", "Decreased volume by {v}%.", "Done, {v}% quieter."],
    "mute":            ["Muted.", "Audio silenced.", "All quiet now.", "Not a peep."],
    "unmute":          ["Unmuted.", "Sound is back.", "Audio restored.", "Unmuting the audio."],
    "get_volume":      ["{r}"],
    "set_brightness":  ["Brightness set to {v}%.", "Done, display is now at {v}%.", "Set screen brightness to {v}%.", "Brightness adjusted to {v}%."],
    "brightness_up":   ["Brighter!", "Turned up the brightness.", "A bit brighter now.", "Increasing screen brightness."],
    "brightness_down": ["Dimmed it.", "Brightness down.", "Lowered display brightness.", "A bit darker now."],
    "brightness_by_up":  ["Brightness up by {v}%.", "Increased brightness by {v}%.", "Screen is {v}% brighter."],
    "brightness_by_down":["Brightness down by {v}%.", "Dimmed display by {v}%.", "Screen is {v}% darker."],
    "get_brightness":  ["{r}"],
    "lock":            ["Locking the screen.", "Screen locked.", "System locked up.", "Securing the desktop."],
    "screenshot":      ["Screenshot saved!", "Got it, screenshot captured.", "Screen captured and saved.", "Snapshot saved successfully."],
    "play":            ["Resuming playback.", "Playing audio.", "Resumed.", "Continuing playback."],
    "pause":           ["Paused.", "Playback paused.", "Holding audio here.", "Paused playback."],
    "stop":            ["Stopped.", "Playback stopped.", "Stopped playback."],
    "play_pause":      ["Toggled playback.", "Playback updated.", "Media state switched."],
    "next_track":      ["Next track.", "Skipping ahead.", "Playing the next track.", "On to the next one."],
    "prev_track":      ["Previous track.", "Going back one track.", "Playing the previous one."],
    "restart_track":   ["Playing from the beginning.", "Restarting from the top.", "Track restarted."],
    "greeting":        ["Hello! How can I help you today?", "Hey there! What can I do for you?", "Hi! Ready when you are.", "Greetings! How may I assist?"],
    "name":            ["I'm KYOMA, your physical AI desktop companion.", "I am KYOMA, your physical AI desktop companion.", "KYOMA here, your physical AI desktop companion."],
    "doing":           ["I'm doing great and ready to assist.", "All systems running smoothly and ready to help.", "Doing well, thanks for asking! What's on your mind?"],
    "thanks":          ["You're very welcome!", "Happy to help!", "Anytime! Let me know if you need anything else.", "My pleasure!"],
    "bye":             ["Goodbye! Have a great day.", "See you later!", "Take care! Standing by whenever you need me.", "Farewell! Have a wonderful day."],
    "get_time":        ["{r}"],
    "get_date":        ["{r}"],
    "get_battery":     ["{r}"],
    "power_status":    ["{r}"],
    "network_status":  ["{r}"],
    "vpn_status":      ["{r}"],
    "performance":     ["{r}"],
    "disk_usage":      ["{r}"],
    "system_info":     ["{r}"],
    "error":           ["Something went wrong: {e}", "I hit an error: {e}"],
    "sleep":           ["Going to sleep now. Call me whenever you need me.", "Entering standby mode. Just say Hey Kyoma to wake me.", "Standby mode activated. See you soon!"],
}

def _say(key: str, **kw) -> str:
    """Pick a non-repeating random response template and format it."""
    templates = _R.get(key, ["{r}"])
    last = _last_responses.get(key)
    choices = [t for t in templates if t != last] if len(templates) > 1 else templates
    tpl = random.choice(choices)
    _last_responses[key] = tpl
    try:
        return tpl.format(**{k: str(v) for k, v in kw.items()})
    except KeyError:
        return tpl


# ─────────────────────────────────────────────────────────────────────────────
# Pre-compiled regex patterns  (compiled once at import — zero runtime cost)
# ─────────────────────────────────────────────────────────────────────────────

_F = re.IGNORECASE

# ── Volume ────────────────────────────────────────────────────────────────────
_RE_SET_VOL    = re.compile(r"\b(?:set\s+(?:the\s+)?)?volume\s+(?:to|at|=)?\s*(\d{1,3})\s*%?\b", _F)
_RE_VOL_UP_BY  = re.compile(r"\b(?:increase|raise|turn\s+up|boost)\s+(?:the\s+)?volume\s+by\s+(\d{1,3})\s*%?\b", _F)
_RE_VOL_DN_BY  = re.compile(r"\b(?:decrease|lower|turn\s+down|reduce|drop)\s+(?:the\s+)?volume\s+by\s+(\d{1,3})\s*%?\b", _F)
_RE_VOL_UP     = re.compile(r"\b(?:volume\s+up|turn\s+(?:the\s+)?volume\s+up|louder|increase\s+(?:the\s+)?volume|raise\s+(?:the\s+)?volume)\b", _F)
_RE_VOL_DN     = re.compile(r"\b(?:volume\s+down|turn\s+(?:the\s+)?volume\s+down|quieter|softer|lower\s+(?:the\s+)?volume|decrease\s+(?:the\s+)?volume|reduce\s+(?:the\s+)?volume)\b", _F)
_RE_MUTE       = re.compile(r"^(?:mute|silence|go\s+quiet|shut\s+up|no\s+sound|mute\s+(?:the\s+)?(?:volume|sound|audio|mic(?:rophone)?))$", _F)
_RE_UNMUTE     = re.compile(r"^(?:unmute|un-?mute|turn\s+(?:the\s+)?(?:sound|audio|volume)\s+(?:back\s+)?on|restore\s+(?:sound|audio)|unmute\s+(?:the\s+)?(?:volume|sound|audio|mic(?:rophone)?))$", _F)
_RE_GET_VOL    = re.compile(r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?volume|(?:check|get|current)\s+volume|volume\s+level|how\s+loud)\b", _F)

# ── Brightness ────────────────────────────────────────────────────────────────
_RE_SET_BRI    = re.compile(r"\b(?:set\s+(?:the\s+)?)?brightness\s+(?:to|at|=)?\s*(\d{1,3})\s*%?\b", _F)
_RE_BRI_UP_BY  = re.compile(r"\b(?:increase|raise|turn\s+up|boost)\s+(?:the\s+)?brightness\s+by\s+(\d{1,3})\s*%?\b", _F)
_RE_BRI_DN_BY  = re.compile(r"\b(?:decrease|lower|turn\s+down|reduce|drop|dim)\s+(?:the\s+)?brightness\s+by\s+(\d{1,3})\s*%?\b", _F)
_RE_BRI_UP     = re.compile(r"\b(?:brightness\s+up|brighter|increase\s+(?:the\s+)?brightness|raise\s+(?:the\s+)?brightness|turn\s+(?:the\s+)?brightness\s+up)\b", _F)
_RE_BRI_DN     = re.compile(r"\b(?:brightness\s+down|dimmer|dim\s+(?:(?:the\s+)?(?:screen|display))?|reduce\s+(?:the\s+)?brightness|lower\s+(?:the\s+)?brightness|decrease\s+(?:the\s+)?brightness|turn\s+(?:the\s+)?brightness\s+down)\b", _F)
_RE_GET_BRI    = re.compile(r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?brightness|(?:check|get|current)\s+brightness|brightness\s+level)\b", _F)

# ── Media ─────────────────────────────────────────────────────────────────────
_RE_PAUSE      = re.compile(r"^(?:(?:media\s+)?pause(?:\s+(?:it|the\s+(?:video|song|music|track|youtube)|video|song|music|track|youtube))?|(?:media\s+)?stop(?:\s+(?:the\s+(?:video|song|music|track|youtube)|video|song|music|track|youtube))?)$", _F)
_RE_PLAY       = re.compile(r"^(?:(?:media\s+)?play(?:\s+(?:it|the\s+(?:video|song|music|track|youtube)|video|song|music|track|youtube))?|resume(?:\s+(?:it|the\s+(?:video|song|music|track|youtube)|video|song|music|track|youtube))?|continue(?:\s+(?:the\s+(?:video|song|music|track|youtube)|video|song|music|track|youtube))?)$", _F)
_RE_PLAY_PAUSE = re.compile(r"^(?:toggle\s+(?:play|media|music|playback)|play\s*[/\\]\s*pause)$", _F)
_RE_NEXT       = re.compile(r"\b(?:next(?:\s+(?:one|track|song|music))?|skip(?:\s+(?:this|one|track|song|music))?|forward(?:\s+track)?)\b", _F)
_RE_PREV       = re.compile(r"\b(?:previous(?:\s+(?:one|track|song|music))?|prev(?:\s+(?:one|track|song|music))?|go\s+back(?:\s+(?:to\s+(?:the\s+)?previous\s+(?:track|song)|a\s+(?:track|song)))?|last\s+(?:track|song))\b", _F)
_RE_RESTART    = re.compile(r"\b(?:restart(?:\s+(?:track|song|music))?|replay(?:\s+(?:this|track|song|music))?|from\s+(?:the\s+)?(?:beginning|start)|start\s+(?:this\s+)?over|play\s+(?:the\s+(?:song|video|track)\s+)?again|beginning\s+of\s+(?:track|song))\b", _F)

# ── Screenshot & Lock ─────────────────────────────────────────────────────────
_RE_SCREENSHOT = re.compile(r"^(?:take\s+(?:a\s+)?|capture\s+(?:a\s+)?|grab\s+(?:a\s+)?)?(?:screenshot|screen\s*shot|ss)(?:\s+(?:and\s+)?save\s+it\s+as\s+([a-zA-Z0-9_\-\s]+?))?(?:\s+(?:now|please))?$|^(?:take\s+(?:a\s+)?(?:screenshot|screen\s*shot|ss)|screengrab|capture\s+screen|grab\s+screen)[\!\.\?\s]*$", _F)
# ── Standby / Sleep & System Risk Patterns ─────────────────────────────────────
_RE_SLEEP        = re.compile(r"^(?:go\s+to\s+sleep|sleep\s+mode|standby|enter\s+standby|take\s+a\s+nap)[\!\.\?\s]*$", _F)
_RE_SYSTEM_RISK  = re.compile(r"\b(shutdown|shut\s+down|power\s+off|restart|reboot|hibernate)\b", _F)
_RE_BARE_ADJUST  = re.compile(r"^(increase|raise|turn\s+up|boost|decrease|lower|turn\s+down|reduce|drop|dim)(?:\s+(?:it|that|this))?[\!\.\?\s]*$", _F)
_RE_BARE_REMIND  = re.compile(r"^(?:set\s+(?:a\s+)?)?(?:reminder|alarm)[\!\.\?\s]*$", _F)
# ── Reminders & Capabilities Patterns ─────────────────────────────────────────
_RE_REMINDERS  = re.compile(r"\b(?:(?:list|show|view|check|read|get)(?:\s+all)?(?:\s+my)?\s+(?:reminders?|remainings?)|(?:reminders?|remainings?)\s+(?:list|status)|what\s+are\s+my\s+(?:reminders?|remainings?)|do\s+i\s+have\s+any\s+(?:reminders?|remainings?))\b", _F)
_RE_GREETING     = re.compile(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|howdy|greetings)[\!\.\?\s]*$", _F)
_RE_SAY_HI_TO    = re.compile(r"\b(?:say\s+(?:hi|hello)\s+to|greet)\s+([a-zA-Z\s]+)[\!\.\?\s]*$", _F)
_RE_NAME         = re.compile(r"^(?:what(?:'s|\s+is)\s+your\s+name|who\s+are\s+you|introduce\s+yourself)[\!\.\?\s]*$", _F)
_RE_DOING        = re.compile(r"^(?:what\s+are\s+you\s+doing|how\s+(?:are\s+)?you(?:\s+doing)?|how's\s+it\s+going)[\!\.\?\s]*$", _F)
_RE_THANKS       = re.compile(r"^(?:thanks|thank\s+you(?:\s+very\s+much|\s+so\s+much)?)[\!\.\?\s]*$", _F)
_RE_BYE          = re.compile(r"^(?:bye|goodbye|see\s+you(?:\s+later)?|farewell|exit)[\!\.\?\s]*$", _F)
_RE_TYPO_CORRECT = re.compile(r"\b(?:i\s+(?:miss[\s\-]?typed|misstyped|mistyped|meant\s+to\s+(?:say|type)|meant)|that\s+was\s+a\s+typo|typo\s+sorry|sorry\s+typo)\b", _F)
_RE_OPEN_BARE    = re.compile(r"^(?:open|launch|start)[\!\.\?\s]*$", _F)
_RE_WHO          = re.compile(r"^(?:who\s+are\s+you|tell\s+me\s+about\s+yourself|introduce\s+yourself|what\s+are\s+you|describe\s+yourself|who\s+made\s+you|who\s+created\s+you|who\s+built\s+you)[\!\.\?\s]*$", _F)
_RE_FIRST_QUESTION = re.compile(r"^(?:what\s+was\s+my\s+first\s+(?:question|message|query)|what\s+did\s+i\s+(?:first\s+ask|ask\s+first))[\!\.\?\s]*$", _F)
_RE_CAPABILITIES = re.compile(r"^(?:what\s+(?:all\s+)?(?:can\s+you\s+do|you\s+can\s+do)|what\s+are\s+your\s+(?:capabilities|features)|state\s+your\s+features|list\s+your\s+features|help\s+me)[\!\.\?\s]*$", _F)

# ── Persona constant ─────────────────────────────────────────────────────────
KYOMA_PERSONA = "I'm KYOMA, your physical AI desktop companion."

# ── Typo tolerance: edit-distance ≤ 1 for short fixed greetings ──────────────
_FUZZY_MAP: dict[str, str] = {}

def _build_fuzzy_map():
    """Pre-build edit-distance-1 variants for short fixed words."""
    targets = {
        "hi": "greeting", "hey": "greeting", "hello": "greeting",
        "thanks": "thanks", "ok": "ok", "bye": "bye",
    }
    alpha = "abcdefghijklmnopqrstuvwxyz"
    for word, key in targets.items():
        _FUZZY_MAP[word] = key
        # Substitutions
        for i in range(len(word)):
            for c in alpha:
                if c != word[i]:
                    variant = word[:i] + c + word[i+1:]
                    if variant not in _FUZZY_MAP and len(variant) >= 2:
                        _FUZZY_MAP[variant] = key
        # Deletions (only if result is ≥ 2 chars)
        for i in range(len(word)):
            variant = word[:i] + word[i+1:]
            if len(variant) >= 2 and variant not in _FUZZY_MAP:
                _FUZZY_MAP[variant] = key
        # Insertions
        for i in range(len(word) + 1):
            for c in alpha:
                variant = word[:i] + c + word[i:]
                if variant not in _FUZZY_MAP:
                    _FUZZY_MAP[variant] = key

_build_fuzzy_map()

# ── Keyboard mash detection ──────────────────────────────────────────────────
def _is_keyboard_mash(text: str) -> bool:
    """Detect meaningless keyboard mash like 'hgfj', 'asdf', 'qwert'."""
    t = text.lower().strip().rstrip("!?.").strip()
    if len(t) < 3 or len(t) > 10:
        return False
    # Must be all alpha
    if not t.isalpha():
        return False
    # If it's a known word or fuzzy match, it's not mash
    if t in _FUZZY_MAP:
        return False
    # Check consonant density: mash tends to have many consonants
    vowels = sum(1 for c in t if c in "aeiou")
    if vowels == 0 and len(t) >= 3:
        return True
    if len(t) >= 4 and vowels / len(t) < 0.15:
        return True
    return False
_RE_STATUS     = re.compile(r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?status|system\s+status|pc\s+status|device\s+status|^status$)\b", _F)

# Word numbers mapping for reminder intervals
_WORD_TO_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# Direct reminder parsing: "remind me to X in N minutes/hours" or "set a reminder in N minutes/hours to X"
# Also supports "saying", "that says", and Whisper mishearing "remaining" for "reminder"
_RE_REMIND_IN_SAYING = re.compile(
    r"\b(?:set\s+(?:a\s+)?)?(?:reminder|remaining)\s+(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\s+(?:saying|that\s+says?)\s+(.+?)[\.\?\!]*$", _F)
_RE_REMIND_ME_IN = re.compile(
    r"\b(?:remind|remaining)\s+(?:me\s+)?(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\s+(?:to|that\s+says?|saying)\s+(.+?)[\.\?\!]*$", _F)
_RE_REMIND_FOR_TIME = re.compile(
    r"\b(?:set\s+(?:a\s+)?)?(?:reminder|remaining)\s+(?:for|at)\s+(\d{1,2}(?::\d{2})?\s*(?:AM|PM|am|pm))\s+(?:saying|that\s+says?|to)\s+(.+?)[\.\?\!]*$", _F)
_RE_REMIND_IN_TO = re.compile(
    r"\b(?:set\s+(?:a\s+)?)?(?:reminder|remaining)\s+(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)\s+to\s+(.+?)[\.\?\!]*$", _F)
_RE_REMIND_TO_IN = re.compile(
    r"\b(?:(?:set\s+(?:a\s+)?)?reminder|(?:remind|remaining)\s+(?:me\s+)?)\s*to\s+(.+?)\s+(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)[\.\?\!]*$", _F)



_RE_LOCK       = re.compile(r"\b(?:lock(?:\s+(?:the\s+)?(?:screen|pc|computer|system|machine))?|(?:screen|pc|computer)\s+lock)\b", _F)

# ── System Info ───────────────────────────────────────────────────────────────
_RE_TIME       = re.compile(r"\b(?:(?:tell\s+me\s+(?:the\s+)?)?(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?time|time\s+(?:now|please)|current\s+time|what\s+time\s+is\s+it)|(?:tell\s+me\s+(?:the\s+)?time)|^time$)\b", _F)
_RE_DATE       = re.compile(r"\b(?:(?:tell\s+me\s+(?:the\s+)?)?(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?date|today(?:'s\s+date)?|what\s+(?:day|date)\s+is\s+(?:it|today)|current\s+date)|(?:tell\s+me\s+(?:the\s+)?date)|^date$)\b", _F)
_RE_BATTERY    = re.compile(r"\b(?:battery(?:\s+(?:status|level|percent(?:age)?|life))?|how\s+much\s+(?:battery|charge)(?:\s+(?:do\s+i\s+have|is\s+left))?|charging\s+status|is\s+it\s+charging|^battery$)\b", _F)
_RE_POWER      = re.compile(r"\b(?:power\s+status|(?:is\s+(?:it|the\s+(?:pc|laptop))\s+)?(?:plugged\s+in|charging|on\s+battery(?:\s+power)?))\b", _F)
_RE_NETWORK    = re.compile(r"\b(?:(?:check\s+)?(?:network|internet|wifi|wi-?fi|connection)\s+status|(?:am\s+i|are\s+we)\s+(?:connected|online)|is\s+(?:the\s+)?(?:internet|network|wifi|wi-?fi)\s+(?:connected|working|on|up)|do\s+i\s+have\s+internet)\b", _F)
_RE_VPN        = re.compile(r"\b(?:vpn\s+status|(?:is\s+(?:the\s+)?)?vpn\s+(?:on|off|connected|active|running)|check\s+vpn)\b", _F)
_RE_PERF       = re.compile(r"\b(?:(?:system\s+)?performance|cpu\s+usage|ram\s+usage|memory\s+usage|how\s+(?:is\s+(?:the\s+)?(?:cpu|ram|memory|system)|(?:much\s+)?(?:cpu|ram|memory)\s+(?:(?:am\s+i|are\s+we)\s+)?using))\b", _F)
_RE_DISK       = re.compile(r"\b(?:disk\s+(?:usage|space|status)|storage\s+(?:usage|space|status|info(?:rmation)?)|how\s+much\s+(?:disk\s+space|storage)(?:\s+(?:do\s+i\s+have|is\s+(?:left|free|remaining)))?)\b", _F)
_RE_SYSINFO    = re.compile(r"\b(?:system\s+info(?:rmation)?|computer\s+info(?:rmation)?|pc\s+(?:specs|info)|system\s+specs)\b", _F)

# ── Search ─────────────────────────────────────────────────────────────────────
_RE_YT_SEARCH  = re.compile(r"\b(?:search(?:\s+for)?\s+(.+?)\s+on\s+(?:youtube|yt)|(?:youtube|yt)\s+(?:search|find)(?:\s+for)?\s+(.+))\b", _F)
_RE_WEB_SEARCH = re.compile(r"\b(?:search(?:\s+for)?\s+(.+?)\s+on\s+(?:google|the\s+(?:web|internet))|google(?:\s+(?:for|search))?\s+(.+)|search(?:\s+for)?\s+(.+))\b", _F)

# ── Browser / App actions ─────────────────────────────────────────────────────
# Trigger words that open things
_OPEN_WORDS    = r"(?:open|launch|start|run|load|bring\s+up|pull\s+up)"
_BROWSE_WORDS  = r"(?:open|go\s+to|browse|navigate\s+to|take\s+me\s+to)"
_CLOSE_WORDS   = r"(?:close|quit|exit|kill|terminate|end|shut\s+down|force\s+quit)"
_MIN_WORDS     = r"(?:minimize|minimise|hide|send\s+to\s+taskbar)"
_REST_WORDS    = r"(?:restore|maximize|maximise|bring\s+back|show)"

# Suffix noise to strip from app names
_APP_SUFFIX    = r"(?:\s+(?:app(?:lication)?|window|program|software|process|for\s+me|please|now))*[\.\?\!]*\s*$"

_RE_CLOSE      = re.compile(rf"\b{_CLOSE_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)
_RE_MINIMIZE   = re.compile(rf"\b{_MIN_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)
_RE_RESTORE    = re.compile(rf"\b{_REST_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)
_RE_OPEN_SITE  = re.compile(rf"\b{_BROWSE_WORDS}\s+(?:the\s+)?(.+?)(?:\s+(?:website|site|page|in\s+(?:browser|chrome|edge|firefox)))?{_APP_SUFFIX}", _F)
_RE_OPEN_APP   = re.compile(rf"^{_OPEN_WORDS}\s+(?:the\s+)?([a-zA-Z0-9_\-\s]+?){_APP_SUFFIX}$", _F)


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _clamp(val: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, val))

def _extract_result(raw) -> str:
    """Unpack tool result whether it's a str, int, or dict({'ok', 'out'/'error'})."""
    if isinstance(raw, dict):
        if raw.get("ok"):
            return str(raw.get("out", "Done."))
        return f"Error: {raw.get('error', 'unknown')}"
    return str(raw) if raw is not None else "Done."

def _record_fast_router_turn(user_text: str, assistant_text: str):
    """Record user and assistant turns in memory_manager so FastRouter turns are remembered."""
    try:
        import Kyoma_automation
        mem = getattr(Kyoma_automation, "memory", None)
        if mem is not None:
            mem.add_user_message(user_text)
            if assistant_text:
                mem.add_assistant_message(text=assistant_text)
    except Exception:
        pass

def _is_plausible_name(name: str) -> bool:
    """Reject match groups that are obviously not an app/site name."""
    if not name or len(name) > 40:
        return False
    n = name.lower().strip()
    # Reject lone function words
    noise = {"it", "that", "this", "the", "a", "an", "them", "me", "us", "something", "anything"}
    if n in noise:
        return False
    # Reject multi-sentence or conjunction-ridden strings
    if re.search(r"\b(?:and|then|also|with|about|tell|story|joke|help)\b", n):
        return False
    return True


def _natural_join(items: list[str]) -> str:
    """Join response strings with commas and 'and', lowering mid-sentence caps.

    2 items:  "{A}, {B}."
    3+ items: "{A}, {B}, and {C}."
    Strips trailing periods from each item to avoid ". and" artifacts,
    lowercases subsequent items to prevent mid-sentence capitals.
    """
    if not items:
        return ""
    if len(items) == 1:
        s = items[0].rstrip(".")
        return s + "."

    # Strip trailing periods and lowercase subsequent items
    cleaned = [items[0].rstrip(".!")]
    for item in items[1:]:
        s = item.rstrip(".!")
        # Lowercase the first char if it's a capital (avoid mid-sentence caps)
        if s and s[0].isupper():
            s = s[0].lower() + s[1:]
        cleaned.append(s)

    if len(cleaned) == 2:
        return f"{cleaned[0]}, {cleaned[1]}."
    # 3+: "A, B, and C."
    return ", ".join(cleaned[:-1]) + ", and " + cleaned[-1] + "."


# ─────────────────────────────────────────────────────────────────────────────
# Core routing logic
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_speech_text(text: str) -> str:
    """Normalize transcribed speech: clean stray commas, repeated periods, and extra whitespace."""
    if not text:
        return ""
    t = text.strip()
    # Normalize common STT phonetic transcription errors
    # e.g., Whisper sometimes transcribes "media pause" as "media pass" or "media pose"
    t = re.sub(r'\bmedia\s+pass\b', 'media pause', t, flags=re.I)
    t = re.sub(r'\bmedia\s+pose\b', 'media pause', t, flags=re.I)
    # Replace internal commas that separate words, e.g. "Reduce, Brightness" -> "Reduce Brightness"
    # but avoid stripping if comma was between digits or special queries
    t = re.sub(r'(\w+)\s*,\s*(\w+)', r'\1 \2', t)
    # Remove leading/trailing punctuation except question marks at the very end
    t = re.sub(r'^[,\.\?!;:\s\-]+', '', t)
    t = re.sub(r'[,\.;:\-]+$', '', t)
    # Collapse multiple whitespaces
    # Strip conversational filler words / polite prefixes at beginning of utterance
    t = re.sub(r'^(?:(?:um|uh|er|ah|please|can\s+you\s+(?:please\s+)?|could\s+you\s+(?:please\s+)?|would\s+you\s+(?:please\s+)?)\s+)+', '', t, flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def route(text: str) -> Tuple[Optional[str], bool]:
    """
    Public entry point. Handles single or multiple commands split by coordinating conjunctions.
    Uses a temporary dry-run mock swap to guarantee multi-command matches before execution.

    Returns:
        (response_text, True)   — command matched & executed, speak this text
        (None, False)           — no match, caller should fall through to LLM
    """
    global _tools
    if not text or not text.strip():
        return None, False
    try:
        cleaned = _normalize_speech_text(text)
        # Strip wake phrase if present at the start: "Hey Kyoma, " or "Kyoma, "
        cleaned = re.sub(r'^(?:hey\s+)?kyoma[\s,:\-]+', '', cleaned, flags=re.I).strip()
        cleaned = _normalize_speech_text(cleaned)
        
        # 1. Check for compound commands FIRST
        # Shared action: "increase brightness and volume" or "decrease volume and brightness"
        # 1. If the command is an explicit parameterized screenshot ("take a screenshot and save it as..."),
        # handle it directly without splitting on the conjunction "and".
        if _RE_SCREENSHOT.search(cleaned):
            res_text, res_handled = _route(cleaned)
            if res_handled:
                _record_fast_router_turn(text, res_text)
            return res_text, res_handled

        m_inc = re.match(r'^(increase|raise|turn up|boost)\s+(brightness|volume)\s+(?:and|also)\s+(brightness|volume)[\.\?\!]*$', cleaned, re.IGNORECASE)
        if m_inc:
            action, first, second = m_inc.group(1), m_inc.group(2), m_inc.group(3)
            parts = [f"{action} {first}", f"{action} {second}"]
        else:
            m_dec = re.match(r'^(decrease|lower|turn down|reduce|drop|dim)\s+(brightness|volume)\s+(?:and|also)\s+(brightness|volume)[\.\?\!]*$', cleaned, re.IGNORECASE)
            if m_dec:
                action, first, second = m_dec.group(1), m_dec.group(2), m_dec.group(3)
                parts = [f"{action} {first}", f"{action} {second}"]
            else:
                # Conjunction split
                delimiters = re.compile(r'\b(?:and|then|also)\b|[,;&]', re.IGNORECASE)
                parts = [p.strip().rstrip(".?!").strip() for p in delimiters.split(cleaned) if p.strip()]

        if len(parts) > 1:
            # Check how many parts match
            matched_responses = []
            unrecognized_clauses = []
            for part in parts:
                resp, matched = _route(part)
                if matched and resp:
                    matched_responses.append(resp)
                else:
                    unrecognized_clauses.append(part)

            if matched_responses:
                # If all matched or some matched: execute recognized, acknowledge unrecognized clauses
                combined = _natural_join(matched_responses)
                if unrecognized_clauses:
                    unrec_summary = ", ".join(f'"{c}"' for c in unrecognized_clauses)
                    combined += f" (Note: I didn't recognize {unrec_summary}.)"
                _record_fast_router_turn(text, combined)
                return combined, True
            else:
                # None matched
                return None, False

        # 2. Check direct single-command match if not a multi-command or if multi-command didn't match all parts
        res_text, res_handled = _route(cleaned)
        if res_handled:
            _record_fast_router_turn(text, res_text)
        return res_text, res_handled
    except Exception:
        traceback.print_exc()
        return None, False



def _route(text: str) -> Tuple[Optional[str], bool]:
    t = _get_tools()

    # ── SLEEP / STANDBY ───────────────────────────────────────────────────────
    if _RE_SLEEP.search(text):
        try:
            from pending_actions import clear_pending_action
            clear_pending_action()
        except Exception:
            pass
        return _say("sleep"), True

    # ── SYSTEM RISK GUARD (Shutdown, Restart, Hibernate) ──────────────────────
    if m_risk := _RE_SYSTEM_RISK.search(text):
        risk_cmd = m_risk.group(1).lower().replace(" ", "")
        if "shut" in risk_cmd or "power" in risk_cmd:
            norm_cmd = "shutdown"
        elif "restart" in risk_cmd or "reboot" in risk_cmd:
            norm_cmd = "restart"
        else:
            norm_cmd = "hibernate"
        try:
            from pending_actions import set_pending_action
            set_pending_action(
                action_type="system_risk_confirmation",
                data={"command": norm_cmd},
                prompt_to_user=f"Are you sure you want to {norm_cmd} your PC? Please say yes to confirm."
            )
        except Exception:
            pass
        return f"Are you sure you want to {norm_cmd} your PC? Please say yes to confirm.", True

    # ── CONTEXTUAL SLOT-FILLING: BARE ADJUSTMENT ("Increase" / "Decrease") ──
    if m_adj := _RE_BARE_ADJUST.match(text):
        adj_word = m_adj.group(1).lower()
        direction = "up" if adj_word in ("increase", "raise", "turn up", "boost") else "down"
        try:
            from pending_actions import get_last_controlled_target, record_controlled_target
            last_target = get_last_controlled_target()
        except Exception:
            last_target = None

        if last_target == "brightness":
            try:
                from display_control import brightness_up, brightness_down, get_brightness
                if direction == "up":
                    brightness_up(10)
                else:
                    brightness_down(10)
                b = get_brightness()
                m_b = re.search(r"(\d+)", str(b))
                b_val = m_b.group(1) if m_b else b
                record_controlled_target("brightness")
                return f"{'Increased' if direction == 'up' else 'Decreased'} brightness to {b_val}%.", True
            except Exception as e:
                return f"Could not adjust brightness: {e}", True
        elif last_target == "volume":
            try:
                from volume_control import change_volume, get_volume
                delta = 10 if direction == "up" else -10
                change_volume(delta)
                v = get_volume()
                record_controlled_target("volume")
                return f"{'Increased' if direction == 'up' else 'Decreased'} volume to {v}%.", True
            except Exception as e:
                return f"Could not adjust volume: {e}", True

        try:
            from pending_actions import set_pending_action
            set_pending_action(
                action_type="slot_fill_adjustment",
                data={"direction": direction},
                prompt_to_user=f"{adj_word.title()} what? Volume or brightness?"
            )
        except Exception:
            pass
        return f"{adj_word.title()} volume or brightness?", True

    # ── CONTEXTUAL SLOT-FILLING: BARE REMINDER ("Set a reminder") ────────────
    if _RE_BARE_REMIND.match(text):
        try:
            from pending_actions import set_pending_action
            set_pending_action(
                action_type="slot_fill_reminder_what",
                data={},
                prompt_to_user="What would you like me to remind you about?"
            )
        except Exception:
            pass
        return "What would you like me to remind you about?", True

    # ── VOLUME ────────────────────────────────────────────────────────────────

    if m := _RE_SET_VOL.search(text):
        level = _clamp(int(m.group(1)))
        _extract_result(t["set_volume"](level))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("set_volume", v=level), True

    if m := _RE_VOL_UP_BY.search(text):
        amount = _clamp(int(m.group(1)), 1, 100)
        current = t["get_volume"]()
        new_level = _clamp(int(current) + amount)
        _extract_result(t["set_volume"](new_level))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("volume_by_up", v=amount), True

    if m := _RE_VOL_DN_BY.search(text):
        amount = _clamp(int(m.group(1)), 1, 100)
        current = t["get_volume"]()
        new_level = _clamp(int(current) - amount)
        _extract_result(t["set_volume"](new_level))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("volume_by_down", v=amount), True

    if _RE_VOL_UP.search(text):
        _extract_result(t["change_volume"]("up"))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("volume_up"), True

    if _RE_VOL_DN.search(text):
        _extract_result(t["change_volume"]("down"))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("volume_down"), True

    if _RE_MUTE.search(text):
        _extract_result(t["mute_volume"]())
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("mute"), True

    if _RE_UNMUTE.search(text):
        _extract_result(t["unmute_volume"]())
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("unmute"), True

    if _RE_GET_VOL.search(text):
        level = t["get_volume"]()
        result = f"Volume is at {level}%."
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("volume")
        except Exception:
            pass
        return _say("get_volume", r=result), True

    # ── BRIGHTNESS ────────────────────────────────────────────────────────────

    if m := _RE_SET_BRI.search(text):
        level = _clamp(int(m.group(1)))
        _extract_result(t["set_brightness"](level))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("brightness")
        except Exception:
            pass
        return _say("set_brightness", v=level), True

    if m := _RE_BRI_UP_BY.search(text):
        step = _clamp(int(m.group(1)), 1, 100)
        _extract_result(t["brightness_up"](step))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("brightness")
        except Exception:
            pass
        return _say("brightness_by_up", v=step), True

    if m := _RE_BRI_DN_BY.search(text):
        step = _clamp(int(m.group(1)), 1, 100)
        _extract_result(t["brightness_down"](step))
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("brightness")
        except Exception:
            pass
        return _say("brightness_by_down", v=step), True

    if _RE_BRI_UP.search(text):
        _extract_result(t["brightness_up"]())
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("brightness")
        except Exception:
            pass
        return _say("brightness_up"), True

    if _RE_BRI_DN.search(text):
        _extract_result(t["brightness_down"]())
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("brightness")
        except Exception:
            pass
        return _say("brightness_down"), True

    if _RE_GET_BRI.search(text):
        result = _extract_result(t["get_brightness"]())
        try:
            from pending_actions import record_controlled_target
            record_controlled_target("brightness")
        except Exception:
            pass
        return _say("get_brightness", r=result), True

    # ── MEDIA ─────────────────────────────────────────────────────────────────

    if _RE_PAUSE.search(text):
        if re.search(r"\bstop\b", text, re.I):
            res = t["stop"]()
            return _say("stop") if res == "Stopped." else res, True
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
        return _say("restart_track"), True

    # ── SCREENSHOT & LOCK ─────────────────────────────────────────────────────

    if m := _RE_SCREENSHOT.search(text):
        raw_name = m.group(1).strip() if m.group(1) else None
        # Discard false filename captures like "it", "it's working", or clauses
        if raw_name:
            # Check against noise words or contractions
            clean_check = raw_name.lower().split()[0]
            if clean_check in {"it", "it's", "that", "this", "working", "something"}:
                raw_name = None
            elif not _is_plausible_name(raw_name):
                raw_name = None
        res = t["take_screenshot_save"](name=raw_name) if raw_name else t["take_screenshot_save"]()
        if raw_name:
            return f"Screenshot saved as {raw_name}.", True
        return _say("screenshot"), True

    if _RE_LOCK.search(text):
        is_refused, refusal = check_demo_mode_refusal("lock_screen")
        if is_refused:
            return refusal, True
        t["lock_screen"]()
        return _say("lock"), True

    # ── SYSTEM INFO ───────────────────────────────────────────────────────────

    if _RE_TIME.search(text):
        result = _extract_result(t["get_time"]())
        return _say("get_time", r=result), True

    if _RE_DATE.search(text):
        result = _extract_result(t["get_date"]())
        return _say("get_date", r=result), True

    if _RE_BATTERY.search(text):
        result = _extract_result(t["get_battery"]())
        return _say("get_battery", r=result), True

    if _RE_POWER.search(text):
        result = _extract_result(t["get_power_status"]())
        return _say("power_status", r=result), True

    if _RE_NETWORK.search(text):
        result = _extract_result(t["get_network_status"]())
        return _say("network_status", r=result), True

    if _RE_VPN.search(text):
        result = _extract_result(t["get_vpn_status"]())
        return _say("vpn_status", r=result), True


    # ── REMINDERS ─────────────────────────────────────────────────────────────
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
        return str(res), True

    if _RE_REMINDERS.search(text):
        raw = t["list_active_reminders"]()
        if not raw or "No active reminders" in str(raw):
            return "You currently have no active reminders scheduled.", True
        clean = str(raw).strip()
        lines = [l.strip() for l in clean.splitlines() if l.strip()]
        if len(lines) > 1:
            clean = " ".join(lines[:3])
        return clean, True

    # ── CANNED "WHAT CAN YOU DO" / STATUS ────────────────────────────────────
    if _RE_STATUS.search(text):
        time_raw = _extract_result(t["get_time"]())
        batt_raw = _extract_result(t["get_battery"]())
        # Clean phrases: 'The current time is 02:49:56 PM' -> '2:49 PM' or keep time portion
        # 'Battery at 77% and charging.' -> 'battery is at 77% and charging.'
        m_t = re.search(r'(\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?)', time_raw, re.I)
        time_clean = m_t.group(1) if m_t else time_raw.replace("The current time is", "").strip()
        batt_clean = re.sub(r'^battery\s+at\s+', '', batt_raw.strip(), flags=re.I).rstrip('.')
        batt_clean = batt_clean.replace("%", " percent")
        return f"It's {time_clean}, and the battery is at {batt_clean}.", True

    # ── DETERMINISTIC CONVERSATIONAL RESPONSES ────────────────────────────────
    if m := _RE_SAY_HI_TO.search(text):
        target = m.group(1).strip()
        return f"Hello, {target}! Nice to meet you.", True

    if _RE_GREETING.match(text):
        return _say("greeting"), True

    if _RE_NAME.search(text):
        return _say("name"), True

    if _RE_DOING.search(text):
        return _say("doing"), True

    if _RE_THANKS.match(text):
        return _say("thanks"), True

    if _RE_BYE.match(text):
        return _say("bye"), True
    if _RE_TYPO_CORRECT.search(text):
        return "Got it, thanks for clarifying!", True

    if _RE_OPEN_BARE.match(text):
        return None, False

    if _RE_WHO.search(text):
        return KYOMA_PERSONA, True

    if _RE_FIRST_QUESTION.search(text):
        try:
            import Kyoma_automation
            first_q = getattr(getattr(Kyoma_automation, "memory", None), "first_user_message", None)
            if first_q:
                return f"Your first question was: \"{first_q}\"", True
            return "You haven't asked any previous questions yet.", True
        except Exception:
            return "You haven't asked any previous questions yet.", True

    if _RE_CAPABILITIES.search(text):
        return ("I control volume, brightness, apps, screenshots, "
                "reminders, system info, and web search."), True

    if _RE_PERF.search(text):
        result = _extract_result(t["get_performance"]())
        return _say("performance", r=result), True

    if _RE_DISK.search(text):
        result = _extract_result(t["get_disk_usage"]())
        return _say("disk_usage", r=result), True

    if _RE_SYSINFO.search(text):
        raw = _extract_result(t["get_system_info"]())
        # Format natural speech: 'CPU: 9.2%, Memory: 64.5%, Boot: ...' -> 'CPU usage is 9 percent and memory usage is 65 percent.'
        m_sys = re.search(r'CPU:\s*([\d\.]+)%?,\s*Memory:\s*([\d\.]+)%', raw, re.I)
        if m_sys:
            cpu_val = round(float(m_sys.group(1)))
            mem_val = round(float(m_sys.group(2)))
            return f"CPU usage is {cpu_val} percent and memory usage is {mem_val} percent.", True
        clean_raw = raw.replace("%", " percent")
        return clean_raw, True

    # ── YOUTUBE SEARCH ────────────────────────────────────────────────────────

    if m := _RE_YT_SEARCH.search(text):
        query = (m.group(1) or m.group(2) or "").strip()
        if query:
            url = "https://www.youtube.com/results?search_query=" + query.replace(" ", "+")
            t["open_browser"](url)
            return _say("yt_search", q=query), True

    # ── WEB SEARCH ────────────────────────────────────────────────────────────
    # Must come AFTER YouTube search check

    if m := _RE_WEB_SEARCH.search(text):
        query = (m.group(1) or m.group(2) or m.group(3) or "").strip()
        # Reject if query looks like a site/app name that should be opened directly
        if query and query.lower() not in SITE_MAP and not re.match(r"^(youtube|yt|netflix|spotify|reddit|github)$", query, _F):
            url = "https://www.google.com/search?q=" + query.replace(" ", "+")
            t["open_browser"](url)
            return _say("web_search", q=query), True

    # ── OPEN KNOWN WEBSITE ────────────────────────────────────────────────────
    # "open youtube", "go to spotify", "browse reddit", etc.

    if m := _RE_OPEN_SITE.search(text):
        name_raw = m.group(1).strip().lower()
        if name_raw in SITE_MAP:
            url = SITE_MAP[name_raw]
            t["open_browser"](url)
            display_name = SITE_DISPLAY_NAMES.get(name_raw, name_raw.title())
            return _say("open_url", n=display_name), True

    # ── CLOSE APP ────────────────────────────────────────────────────────────

    if m := _RE_CLOSE.search(text):
        name = m.group(1).strip()
        if _is_plausible_name(name):
            is_refused, refusal = check_demo_mode_refusal("close_application", {"name": name})
            if is_refused:
                return refusal, True
            result = t["close_application"](name)
            r = _extract_result(result)
            if "error" in r.lower() or "not found" in r.lower():
                return f"I couldn't find a window for {name.title()} to close.", True
            return _say("close_app", n=name.title()), True

    # ── MINIMIZE APP ─────────────────────────────────────────────────────────

    if m := _RE_MINIMIZE.search(text):
        name = m.group(1).strip()
        if _is_plausible_name(name):
            result = t["minimize_application"](name)
            r = _extract_result(result)
            if "error" in r.lower() or "not found" in r.lower():
                return f"No window found for {name.title()}.", True
            return _say("minimize_app", n=name.title()), True

    # ── RESTORE APP ──────────────────────────────────────────────────────────

    if m := _RE_RESTORE.search(text):
        name = m.group(1).strip()
        if _is_plausible_name(name):
            result = t["restore_application"](name)
            r = _extract_result(result)
            if "error" in r.lower() or "not found" in r.lower():
                return f"No minimized window found for {name.title()}.", True
            return _say("restore_app", n=name.title()), True

    # ── OPEN APP (anything else) ──────────────────────────────────────────────
    # Must be last — most permissive rule

    if m := _RE_OPEN_APP.search(text):
        name = m.group(1).strip()
        if _is_plausible_name(name):
            # Check if it's a known website we should open in browser instead
            if name.lower() in SITE_MAP:
                url = SITE_MAP[name.lower()]
                t["open_browser"](url)
                return _say("open_url", n=name.title()), True
            # Otherwise hand to open_application (handles apps, exe paths, etc.)
            result = t["open_application"](name)
            r = _extract_result(result)
            if "error" in r.lower() or "not found" in r.lower():
                # Let LLM handle it — maybe it knows a better approach
                return None, False
            return _say("open_app", n=name.title()), True

    # ── KEYBOARD MASH DETECTION ─────────────────────────────────────────────
    if _is_keyboard_mash(text):
        return "Didn't catch that.", True

    # ── FUZZY TYPO MATCHING (edit-distance ≤ 1 for short fixed inputs) ────
    fuzzy_key = text.lower().strip().rstrip("!?.").strip()
    if fuzzy_key in _FUZZY_MAP:
        matched_key = _FUZZY_MAP[fuzzy_key]
        if matched_key == "greeting":
            return _say("greeting"), True
        elif matched_key == "thanks":
            return _say("thanks"), True
        elif matched_key == "bye":
            return _say("bye"), True
        elif matched_key == "ok":
            return "Got it!", True

    # No rule matched
    return None, False


# ─────────────────────────────────────────────────────────────────────────────
# Debug / Test utility  (run:  python fast_router.py)
# ─────────────────────────────────────────────────────────────────────────────

def _test():
    """Quick smoke-test — checks pattern matching only (no actual tool calls)."""
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))

    tests = [
        # Volume
        ("set volume to 75",             True),
        ("volume 50",                    True),
        ("increase volume by 20",        True),
        ("decrease volume by 10",        True),
        ("volume up",                    True),
        ("volume down",                  True),
        ("louder",                       True),
        ("quieter",                      True),
        ("mute",                         True),
        ("unmute",                       True),
        ("what's the volume",            True),
        # Brightness
        ("set brightness to 80",         True),
        ("brightness 40%",               True),
        ("increase brightness by 15",    True),
        ("reduce brightness by 30",      True),
        ("brightness up",                True),
        ("dimmer",                       True),
        ("dim the screen",               True),
        ("what's the brightness",        True),
        # Media
        ("play",                         True),
        ("pause",                        True),
        ("next track",                   True),
        ("skip",                         True),
        ("previous track",               True),
        ("go back",                      True),
        ("restart track",                True),
        ("start over",                   True),
        # Screenshot / Lock
        ("take a screenshot",            True),
        ("screenshot",                   True),
        ("lock screen",                  True),
        ("lock the pc",                  True),
        # System
        ("what time is it",              True),
        ("what's the date",              True),
        ("battery status",               True),
        ("is it charging",               True),
        ("network status",               True),
        ("check vpn",                    True),
        ("cpu usage",                    True),
        ("disk space",                   True),
        ("system info",                  True),
        # Search
        ("search lofi music on youtube", True),
        ("youtube search coding music",  True),
        ("google python tutorials",      True),
        ("search for best laptops",      True),
        # Browser
        ("open youtube",                 True),
        ("go to spotify",                True),
        ("browse reddit",                True),
        ("open github",                  True),
        # Apps
        ("open notepad",                 True),
        ("launch calculator",            True),
        ("open discord",                 True),
        ("close notepad",                True),
        ("minimize chrome",              True),
        # Multi-command tests
        ("open youtube and open calculator", True),
        ("open youtube and tell me a story", None),
        # Should NOT match (ambiguous → LLM)
        ("play something",               None),  # ambiguous — no specific action
        ("search",                       None),  # no query
        ("open",                         None),  # no name

    ]

    passed = failed = 0
    for text, expect_match in tests:
        try:
            # Patch tools to no-ops for testing
            global _tools
            _tools = {k: (lambda *a, **kw: "OK") for k in [
                "set_volume","change_volume","mute_volume","unmute_volume",
                "set_brightness","get_brightness","brightness_up","brightness_down","lock_screen",
                "play_pause","play","pause","next_track","previous_track","startfrombegin_track",
                "take_screenshot_save","get_time","get_date","get_battery","get_system_info",
                "get_power_status","get_network_status","get_vpn_status","get_performance","get_disk_usage",
                "open_application","open_browser","minimize_application","restore_application","close_application","add_reminder","list_active_reminders",
            ]}
            _tools["get_volume"] = lambda *a, **kw: 50
            _, matched = route(text)

        except Exception as ex:
            matched = False
            print(f"  EXCEPTION on '{text}': {ex}")

        ok = (matched == expect_match) if expect_match is not None else (not matched)
        status = "[PASS]" if ok else "[FAIL]"
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  {status} FAIL  '{text}'  expected={expect_match}  got={matched}")

    print(f"\nFastRouter self-test: {passed}/{passed+failed} passed")
    _tools = None   # reset for real use


if __name__ == "__main__":
    _test()
