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
    from media_control    import play_pause, next_track, previous_track, startfrombegin_track
    from screenshot       import take_screenshot_save
    from system_info_utils import (get_time, get_date, get_battery, get_system_info,
                                   get_power_status, get_network_status, get_vpn_status,
                                   get_performance, get_disk_usage)
    from app_utils        import (open_application, open_browser,
                                  minimize_application, restore_application, close_application)
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

# ─────────────────────────────────────────────────────────────────────────────
# Response templates — randomised so Kyoma doesn't sound like a robot
# ─────────────────────────────────────────────────────────────────────────────

_R: dict[str, list[str]] = {
    "open_app":        ["{n} opened!",       "Launching {n}.",            "On it — {n} is opening.",    "{n}, coming right up!"],
    "open_url":        ["Opening {n}!",      "Here you go — {n}.",        "On it, launching {n}.",      "{n} is on its way!"],
    "web_search":      ["Searching for '{q}' on Google.", "Looking up '{q}'.", "On it — googling '{q}'."],
    "yt_search":       ["Searching YouTube for '{q}'.", "Looking up '{q}' on YouTube.", "Here you go — searching '{q}' on YouTube."],
    "close_app":       ["{n} closed.",        "Done — {n} is gone.",       "Closed {n}."],
    "minimize_app":    ["{n} minimized.",     "Minimized {n}.",            "Out of the way — {n} minimized."],
    "restore_app":     ["{n} is back.",       "Restored {n}.",             "Bringing {n} back."],
    "set_volume":      ["Volume set to {v}%.", "Done — volume is now {v}%.", "Set it to {v}%."],
    "volume_up":       ["Louder!",            "Volume up.",                "Turned it up a notch."],
    "volume_down":     ["Quieter.",           "Volume down.",              "Turned it down."],
    "volume_by_up":    ["Volume up by {v}%.", "Increased volume by {v}%.", "Done — {v}% louder."],
    "volume_by_down":  ["Volume down by {v}%.", "Decreased volume by {v}%.", "Done — {v}% quieter."],
    "mute":            ["Muted.",             "All quiet now.",            "Silenced.", "Not a peep."],
    "unmute":          ["Unmuted.",           "Sound is back.",            "Audio restored."],
    "get_volume":      ["{r}"],
    "set_brightness":  ["Brightness set to {v}%.", "Done — brightness is at {v}%.", "Set screen to {v}%."],
    "brightness_up":   ["Brighter!",          "Turned up the brightness.", "A bit brighter."],
    "brightness_down": ["Dimmed it.",         "Brightness down.",          "A bit darker now."],
    "brightness_by_up":  ["Brightness up by {v}%.", "Increased brightness by {v}%."],
    "brightness_by_down":["Brightness down by {v}%.", "Dimmed by {v}%."],
    "get_brightness":  ["{r}"],
    "lock":            ["Locking the screen.", "Screen locked.",           "Locked up."],
    "screenshot":      ["Screenshot saved!",  "Got it — screenshot taken.", "Captured and saved."],
    "play_pause":      ["Done.",              "Toggled playback.",         "Played/paused."],
    "next_track":      ["Next track!",        "Skipping ahead.",           "Playing the next one."],
    "prev_track":      ["Previous track.",    "Going back one.",           "Playing the previous one."],
    "restart_track":   ["Starting over.",     "Back to the beginning.",    "Restarting from the top."],
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
}

def _say(key: str, **kw) -> str:
    """Pick a random response template and fill it in."""
    templates = _R.get(key, ["{r}"])
    tpl = random.choice(templates)
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
_RE_PLAY_PAUSE = re.compile(r"^(?:play|pause|toggle\s+(?:play|media|music|playback)|play\s*[/\\]\s*pause|resume(?:\s+(?:music|media|playback))?)$", _F)
_RE_NEXT       = re.compile(r"\b(?:next\s+(?:track|song|music)|skip(?:\s+(?:this|track|song|music))?|forward(?:\s+track)?)\b", _F)
_RE_PREV       = re.compile(r"\b(?:previous\s+(?:track|song|music)|prev(?:\s+(?:track|song|music))?|go\s+back(?:\s+(?:a\s+)?(?:track|song))?|last\s+(?:track|song))\b", _F)
_RE_RESTART    = re.compile(r"\b(?:restart(?:\s+(?:track|song|music))?|replay(?:\s+(?:this|track|song|music))?|from\s+(?:the\s+)?(?:beginning|start)|start\s+(?:this\s+)?over|beginning\s+of\s+(?:track|song))\b", _F)

# ── Screenshot & Lock ─────────────────────────────────────────────────────────
_RE_SCREENSHOT = re.compile(r"\b(?:(?:take\s+(?:a\s+)?|capture\s+(?:a\s+)?|grab\s+(?:a\s+)?)?screenshot(?:\s+(?:now|please))?|screen(?:\s+)?shot|screen\s+capture|screengrab)\b", _F)
_RE_LOCK       = re.compile(r"\b(?:lock(?:\s+(?:the\s+)?(?:screen|pc|computer|system|machine))?|(?:screen|pc|computer)\s+lock)\b", _F)

# ── System Info ───────────────────────────────────────────────────────────────
_RE_TIME       = re.compile(r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?time|time\s+(?:now|please)|current\s+time|what\s+time\s+is\s+it)\b", _F)
_RE_DATE       = re.compile(r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?date|today(?:'s\s+date)?|what\s+(?:day|date)\s+is\s+(?:it|today)|current\s+date)\b", _F)
_RE_BATTERY    = re.compile(r"\b(?:battery(?:\s+(?:status|level|percent(?:age)?|life))?|how\s+much\s+(?:battery|charge)(?:\s+(?:do\s+i\s+have|is\s+left))?|charging\s+status|is\s+it\s+charging)\b", _F)
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
_APP_SUFFIX    = r"(?:\s+(?:app(?:lication)?|window|program|software|process|for\s+me|please|now))*\s*$"

_RE_CLOSE      = re.compile(rf"\b{_CLOSE_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)
_RE_MINIMIZE   = re.compile(rf"\b{_MIN_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)
_RE_RESTORE    = re.compile(rf"\b{_REST_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)
_RE_OPEN_SITE  = re.compile(rf"\b{_BROWSE_WORDS}\s+(?:the\s+)?(.+?)(?:\s+(?:website|site|page|in\s+(?:browser|chrome|edge|firefox)))?{_APP_SUFFIX}", _F)
_RE_OPEN_APP   = re.compile(rf"\b{_OPEN_WORDS}\s+(?:the\s+)?(.+?){_APP_SUFFIX}", _F)


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

def _is_plausible_name(name: str) -> bool:
    """Reject match groups that are obviously not an app/site name."""
    if not name or len(name) > 50:
        return False
    # Reject lone function words
    noise = {"it", "that", "this", "the", "a", "an", "them", "me", "us"}
    if name.lower() in noise:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Core routing logic
# ─────────────────────────────────────────────────────────────────────────────

def route(text: str) -> Tuple[Optional[str], bool]:
    """
    Public entry point. Handles single or multiple commands split by coordinating conjunctions.
    Uses a temporary dry-run mock swap to guarantee multi-command matches before execution.

    Returns:
        (response_text, True)   — command matched & executed, speak this text
        (None, False)           — no match, caller should fall through to LLM
    """
    if not text or not text.strip():
        return None, False
    try:
        cleaned = text.strip()
        
        # Split by conjunctions: "and", "then", "also", comma, semicolon, ampersand
        delimiters = re.compile(r'\b(?:and|then|also)\b|[,;&]', re.IGNORECASE)
        parts = [p.strip() for p in delimiters.split(cleaned) if p.strip()]
        
        if len(parts) <= 1:
            return _route(cleaned)
            
        # Multi-command check: Dry-run check first to prevent partial execution side-effects
        global _tools
        real_tools = _get_tools()  # Force load if not already loaded
        backed_up_tools = dict(_tools)
        
        # Build mock tools
        mock_tools = {}
        for k in backed_up_tools.keys():
            if k == "get_volume" or k == "get_brightness":
                mock_tools[k] = lambda *a, **kw: 50
            else:
                mock_tools[k] = lambda *a, **kw: {"ok": True, "out": "OK"}
                
        # Swap tools to dry-run mocks
        _tools = mock_tools
        
        all_matched = True
        for part in parts:
            _, matched = _route(part)
            if not matched:
                all_matched = False
                break
                
        # Restore real tools
        _tools = backed_up_tools
        
        if all_matched:
            # Execute all parts for real
            responses = []
            for part in parts:
                resp, matched = _route(part)
                if matched and resp:
                    responses.append(resp)
            return " and ".join(responses), True
            
        # Fall back to LLM for full text if any segment failed to match
        return None, False
    except Exception:
        traceback.print_exc()
        return None, False



def _route(text: str) -> Tuple[Optional[str], bool]:
    t = _get_tools()

    # ── VOLUME ────────────────────────────────────────────────────────────────

    if m := _RE_SET_VOL.search(text):
        level = _clamp(int(m.group(1)))
        _extract_result(t["set_volume"](level))
        return _say("set_volume", v=level), True

    if m := _RE_VOL_UP_BY.search(text):
        amount = _clamp(int(m.group(1)), 1, 100)
        current = t["get_volume"]()
        new_level = _clamp(int(current) + amount)
        _extract_result(t["set_volume"](new_level))
        return _say("volume_by_up", v=amount), True

    if m := _RE_VOL_DN_BY.search(text):
        amount = _clamp(int(m.group(1)), 1, 100)
        current = t["get_volume"]()
        new_level = _clamp(int(current) - amount)
        _extract_result(t["set_volume"](new_level))
        return _say("volume_by_down", v=amount), True

    if _RE_VOL_UP.search(text):
        _extract_result(t["change_volume"]("up"))
        return _say("volume_up"), True

    if _RE_VOL_DN.search(text):
        _extract_result(t["change_volume"]("down"))
        return _say("volume_down"), True

    if _RE_MUTE.search(text):
        _extract_result(t["mute_volume"]())
        return _say("mute"), True

    if _RE_UNMUTE.search(text):
        _extract_result(t["unmute_volume"]())
        return _say("unmute"), True

    if _RE_GET_VOL.search(text):
        level = t["get_volume"]()
        result = f"Volume is at {level}%."
        return _say("get_volume", r=result), True

    # ── BRIGHTNESS ────────────────────────────────────────────────────────────

    if m := _RE_SET_BRI.search(text):
        level = _clamp(int(m.group(1)))
        _extract_result(t["set_brightness"](level))
        return _say("set_brightness", v=level), True

    if m := _RE_BRI_UP_BY.search(text):
        step = _clamp(int(m.group(1)), 1, 100)
        _extract_result(t["brightness_up"](step))
        return _say("brightness_by_up", v=step), True

    if m := _RE_BRI_DN_BY.search(text):
        step = _clamp(int(m.group(1)), 1, 100)
        _extract_result(t["brightness_down"](step))
        return _say("brightness_by_down", v=step), True

    if _RE_BRI_UP.search(text):
        _extract_result(t["brightness_up"]())
        return _say("brightness_up"), True

    if _RE_BRI_DN.search(text):
        _extract_result(t["brightness_down"]())
        return _say("brightness_down"), True

    if _RE_GET_BRI.search(text):
        result = _extract_result(t["get_brightness"]())
        return _say("get_brightness", r=result), True

    # ── MEDIA ─────────────────────────────────────────────────────────────────

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
        return _say("restart_track"), True

    # ── SCREENSHOT & LOCK ─────────────────────────────────────────────────────

    if _RE_SCREENSHOT.search(text):
        _extract_result(t["take_screenshot_save"]())
        return _say("screenshot"), True

    if _RE_LOCK.search(text):
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

    if _RE_PERF.search(text):
        result = _extract_result(t["get_performance"]())
        return _say("performance", r=result), True

    if _RE_DISK.search(text):
        result = _extract_result(t["get_disk_usage"]())
        return _say("disk_usage", r=result), True

    if _RE_SYSINFO.search(text):
        result = _extract_result(t["get_system_info"]())
        return _say("system_info", r=result), True

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
            return _say("open_url", n=name_raw.title()), True

    # ── CLOSE APP ────────────────────────────────────────────────────────────

    if m := _RE_CLOSE.search(text):
        name = m.group(1).strip()
        if _is_plausible_name(name):
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
                "play_pause","next_track","previous_track","startfrombegin_track",
                "take_screenshot_save","get_time","get_date","get_battery","get_system_info",
                "get_power_status","get_network_status","get_vpn_status","get_performance","get_disk_usage",
                "open_application","open_browser","minimize_application","restore_application","close_application",
            ]}
            _tools["get_volume"] = lambda *a, **kw: 50
            _, matched = route(text)

        except Exception as ex:
            matched = False
            print(f"  EXCEPTION on '{text}': {ex}")

        ok = (matched == expect_match) if expect_match is not None else (not matched)
        status = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
            print(f"  {status} FAIL  '{text}'  expected={expect_match}  got={matched}")

    print(f"\nFastRouter self-test: {passed}/{passed+failed} passed")
    _tools = None   # reset for real use


if __name__ == "__main__":
    _test()
