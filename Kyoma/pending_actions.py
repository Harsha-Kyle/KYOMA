"""
pending_actions.py — Session Pending Actions & Contextual Slot-Filling Manager for Kyoma
────────────────────────────────────────────────────────────────────────────────────────
Maintains explicit, short-lived pending actions (60s expiration) and missing-information
slots per session.

Supports:
- "Increase" -> Kyoma asks "Volume or brightness?" -> "Brightness" -> asks percentage -> "70" -> sets brightness 70%.
- "Set a reminder" -> asks what for -> asks when -> schedules reminder.
- "Yes" / "Sure" -> executes exact action previously offered.
- Refuses dangerous system actions (shutdown, restart, hibernate) without explicit confirmation.
"""

from __future__ import annotations

import time
import re
from typing import Optional, Dict, Any, Tuple

_SESSION_PENDING: Dict[str, Dict[str, Any]] = {}
EXPIRATION_SECONDS = 60.0

def get_pending_action(session_id: str = "default") -> Optional[Dict[str, Any]]:
    record = _SESSION_PENDING.get(session_id)
    if not record:
        return None
    if time.time() - record.get("timestamp", 0) > EXPIRATION_SECONDS:
        _SESSION_PENDING.pop(session_id, None)
        return None
    return record

def set_pending_action(session_id: str = "default", action_type: str = "", data: Optional[Dict[str, Any]] = None, prompt_to_user: str = "") -> None:
    _SESSION_PENDING[session_id] = {
        "action_type": action_type,
        "data": data or {},
        "prompt_to_user": prompt_to_user,
        "timestamp": time.time()
    }

def clear_pending_action(session_id: str = "default") -> None:
    _SESSION_PENDING.pop(session_id, None)

_LAST_CONTROLLED_TARGET: Dict[str, Tuple[str, float]] = {}

def record_controlled_target(target: str, session_id: str = "default") -> None:
    """Remember the last controlled target (brightness or volume) for 60 seconds."""
    if target in ("brightness", "volume"):
        _LAST_CONTROLLED_TARGET[session_id] = (target, time.time())

def get_last_controlled_target(session_id: str = "default") -> Optional[str]:
    """Return the last controlled target if within 60 seconds."""
    rec = _LAST_CONTROLLED_TARGET.get(session_id)
    if not rec:
        return None
    target, ts = rec
    if time.time() - ts <= EXPIRATION_SECONDS:
        return target
    _LAST_CONTROLLED_TARGET.pop(session_id, None)
    return None

def normalize_target_word(word: str) -> Optional[str]:
    """
    Recognize brightness/volume words with narrow fuzzy matching for known typo variants
    such as 'brightnesss'.
    """
    w = word.strip().lower().rstrip(".?!")
    if w in {"brightness", "brightnesss", "screen", "display", "brightnes", "brihtness"}:
        return "brightness"
    if w in {"volume", "volum", "volue", "sound", "audio"}:
        return "volume"
    return None

def extract_numeric_percentage(text: str) -> Optional[int]:
    """Extract a bare number or percentage (e.g. '70', '70%', 'to 70')."""
    clean = text.strip().lower().rstrip(".?!")
    m = re.match(r"^(?:(?:set\s+(?:it\s+)?(?:to\s+)?)?|(?:to\s+)?)?(\d{1,3})\s*%?$", clean)
    if m:
        val = int(m.group(1))
        return max(0, min(100, val))
    word_map = {
        "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40,
        "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100
    }
    if clean in word_map:
        return word_map[clean]
    return None

def handle_pending_followup(text: str, session_id: str = "default") -> Tuple[Optional[str], bool]:
    """
    Check if text fulfills or confirms an active pending action.
    Returns (response_text, True) if handled, or (None, False) if not applicable.
    If the next message is neither a number nor a valid target word for a pending action,
    clears the pending action and returns (None, False) to allow normal routing.
    """
    pending = get_pending_action(session_id)
    if not pending:
        return None, False

    clean = text.strip().lower()
    action_type = pending.get("action_type")
    data = pending.get("data", {})

    # 1. Negative / cancellation handling
    is_negative = bool(re.match(r"^(?:no|nope|cancel|don't|stop|abort|never mind)[\.\!\?]*$", clean))
    if is_negative:
        clear_pending_action(session_id)
        return "Action cancelled.", True

    # 2. Confirmation handling
    is_affirmative = bool(re.match(r"^(?:yes|yep|yeah|sure|confirm|proceed|go ahead|do it|ok|okay)[\.\!\?]*$", clean))

    if action_type == "system_risk_confirmation":
        if is_affirmative:
            cmd = data.get("command")
            clear_pending_action(session_id)
            if cmd == "shutdown":
                return "Shutting down the system now.", True
            elif cmd == "restart":
                return "Restarting the system now.", True
            elif cmd == "hibernate":
                return "Hibernating the system now.", True
        else:
            clear_pending_action(session_id)
            return None, False

    if action_type == "open_failed_search":
        if is_affirmative:
            query_url = data.get("search_url")
            clear_pending_action(session_id)
            if query_url:
                try:
                    import webbrowser
                    webbrowser.open(query_url)
                    return f"Opening search results in your browser.", True
                except Exception as e:
                    return f"Could not open browser: {e}", True
            return "Opening your browser.", True
        else:
            clear_pending_action(session_id)
            return None, False

    if action_type == "slot_fill_adjustment":
        # Waiting for target: volume vs brightness
        target = normalize_target_word(clean)
        num_val = extract_numeric_percentage(clean)

        if target:
            # Transition to asking for the percentage while preserving target
            set_pending_action(
                session_id=session_id,
                action_type="slot_fill_percentage",
                data={"target": target, "direction": data.get("direction", "up")},
                prompt_to_user=f"What percentage would you like to set the {target} to?"
            )
            record_controlled_target(target, session_id)
            return f"What percentage would you like to set the {target} to?", True

        if num_val is not None:
            # User directly replied with a percentage (e.g. "70")
            # Resolve against recent target or fallback to volume
            recent_target = get_last_controlled_target(session_id) or "volume"
            clear_pending_action(session_id)
            record_controlled_target(recent_target, session_id)
            try:
                if recent_target == "brightness":
                    from display_control import set_brightness
                    set_brightness(num_val)
                    return f"Brightness set to {num_val}%.", True
                else:
                    from volume_control import set_volume
                    set_volume(num_val)
                    return f"Volume set to {num_val}%.", True
            except Exception as e:
                return f"Could not set {recent_target}: {e}", True

        # Unrelated message: clear pending action and let normal routing handle it
        clear_pending_action(session_id)
        return None, False

    if action_type == "slot_fill_percentage":
        target = data.get("target") or get_last_controlled_target(session_id) or "volume"
        num_val = extract_numeric_percentage(clean)
        if num_val is not None:
            clear_pending_action(session_id)
            record_controlled_target(target, session_id)
            try:
                if target == "brightness":
                    from display_control import set_brightness
                    set_brightness(num_val)
                    return f"Brightness set to {num_val}%.", True
                else:
                    from volume_control import set_volume
                    set_volume(num_val)
                    return f"Volume set to {num_val}%.", True
            except Exception as e:
                return f"Could not set {target}: {e}", True

        # Check if user changed or restated target word
        new_target = normalize_target_word(clean)
        if new_target:
            set_pending_action(
                session_id=session_id,
                action_type="slot_fill_percentage",
                data={"target": new_target, "direction": data.get("direction", "up")},
                prompt_to_user=f"What percentage would you like to set the {new_target} to?"
            )
            record_controlled_target(new_target, session_id)
            return f"What percentage would you like to set the {new_target} to?", True

        # Unrelated message: clear and route normally
        clear_pending_action(session_id)
        return None, False

    if action_type == "slot_fill_reminder_what":
        if bool(re.match(r"^(?:only\s+once|one\s+time|just\s+once|once)[\.\?\!]*$", clean)):
            return "Understood, one-time reminder. What would you like me to remind you about?", True

        m_rel = re.search(r"^(?:to\s+)?(.+?)\s+(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)[\.\?\!]*$", clean, re.I)
        if m_rel:
            title = m_rel.group(1).strip()
            num_str = m_rel.group(2).strip()
            unit_str = m_rel.group(3).strip()
            when_str = f"in {num_str} {unit_str}"
            clear_pending_action(session_id)
            try:
                from reminder_utils import add_reminder
                res = add_reminder(title=title, message=title, remind_time=when_str)
                return str(res), True
            except Exception as e:
                return f"Failed to set reminder: {e}", True

        m_time_only = re.search(r"^(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)[\.\?\!]*$", clean, re.I)
        if m_time_only:
            when_str = clean
            set_pending_action(
                session_id=session_id,
                action_type="slot_fill_reminder_what_with_when",
                data={"when": when_str},
                prompt_to_user="What should I remind you to do?"
            )
            return "What would you like me to remind you to do?", True

        reminder_title = text.strip()
        set_pending_action(
            session_id=session_id,
            action_type="slot_fill_reminder_when",
            data={"title": reminder_title},
            prompt_to_user="When should I set the reminder for?"
        )
        return f"Got it, '{reminder_title}'. When should I remind you?", True

    if action_type == "slot_fill_reminder_what_with_when":
        when_str = data.get("when", "in 5 minutes")
        title = text.strip()
        clear_pending_action(session_id)
        try:
            from reminder_utils import add_reminder
            res = add_reminder(title=title, message=title, remind_time=when_str)
            return str(res), True
        except Exception as e:
            return f"Failed to set reminder: {e}", True

    if action_type == "slot_fill_reminder_when":
        if bool(re.match(r"^(?:only\s+once|one\s+time|just\s+once|once)[\.\?\!]*$", clean)):
            title = data.get("title", "Reminder")
            return f"Understood, one-time reminder for '{title}'. When should I remind you?", True

        title = data.get("title", "Reminder")
        when_str = text.strip()
        clear_pending_action(session_id)
        try:
            from reminder_utils import add_reminder
            res = add_reminder(title=title, message=title, remind_time=when_str)
            if isinstance(res, dict) and res.get("ok"):
                return f"Reminder set for {title} at {when_str}.", True
            elif isinstance(res, str):
                return res, True
            return f"Reminder set for {title}.", True
        except Exception as e:
            return f"Failed to set reminder: {e}", True

    return None, False
