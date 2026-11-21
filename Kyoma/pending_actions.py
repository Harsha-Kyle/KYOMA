"""
pending_actions.py — Session Pending Actions & Contextual Slot-Filling Manager for Kyoma
────────────────────────────────────────────────────────────────────────────────────────
Maintains explicit, short-lived pending actions (60s expiration) and missing-information
slots per session.

Supports:
- "Increase" -> Kyoma asks "Increase volume or brightness?" -> "Brightness" -> executes increase brightness.
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

def handle_pending_followup(text: str, session_id: str = "default") -> Tuple[Optional[str], bool]:
    """
    Check if text fulfills or confirms an active pending action.
    Returns (response_text, True) if handled, or (None, False) if not applicable.
    """
    pending = get_pending_action(session_id)
    if not pending:
        return None, False

    clean = text.strip().lower()
    action_type = pending.get("action_type")
    data = pending.get("data", {})

    # 1. Confirmation handling ("yes", "sure", "confirm", "go ahead", "do it")
    is_affirmative = bool(re.match(r"^(?:yes|yep|yeah|sure|confirm|proceed|go ahead|do it|ok|okay)[\.\!\?]*$", clean))
    is_negative = bool(re.match(r"^(?:no|nope|cancel|don't|stop|abort|never mind)[\.\!\?]*$", clean))

    if is_negative:
        clear_pending_action(session_id)
        return "Action cancelled.", True

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
            return "Confirmation required. Please say 'yes' to proceed or 'cancel'.", True

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

    if action_type == "slot_fill_adjustment":
        # Waiting for target: volume vs brightness
        direction = data.get("direction", "up")  # "up" or "down"
        if "brightness" in clean or "screen" in clean or "display" in clean:
            clear_pending_action(session_id)
            try:
                from display_control import brightness_up, brightness_down, get_brightness
                if direction == "up":
                    brightness_up(10)
                else:
                    brightness_down(10)
                b = get_brightness()
                m_b = re.search(r"(\d+)", str(b))
                b_val = m_b.group(1) if m_b else b
                record_controlled_target("brightness", session_id)
                return f"{'Increased' if direction == 'up' else 'Decreased'} brightness to {b_val}%.", True
            except Exception as e:
                return f"Could not adjust brightness: {e}", True
        elif "volume" in clean or "sound" in clean or "audio" in clean:
            clear_pending_action(session_id)
            try:
                from volume_control import change_volume, get_volume
                delta = 10 if direction == "up" else -10
                change_volume(delta)
                v = get_volume()
                record_controlled_target("volume", session_id)
                return f"{'Increased' if direction == 'up' else 'Decreased'} volume to {v}%.", True
            except Exception as e:
                return f"Could not adjust volume: {e}", True

    if action_type == "slot_fill_reminder_what":
        # Check if the user said "only once" or "one time" confirming default recurrence
        if bool(re.match(r"^(?:only\s+once|one\s+time|just\s+once|once)[\.\?\!]*$", clean)):
            return "Understood, one-time reminder. What would you like me to remind you about?", True

        # Check if user directly provided both what and when (e.g. "drink water in 5 sec")
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

        # Check if user just gave a time expression (e.g. "in 5 sec")
        m_time_only = re.search(r"^(?:in|and|after)\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(mins?|minutes?|hours?|hrs?|seconds?|secs?)[\.\?\!]*$", clean, re.I)
        if m_time_only:
            # Task is still pending, save time and ask for task
            when_str = clean
            set_pending_action(
                session_id=session_id,
                action_type="slot_fill_reminder_what_with_when",
                data={"when": when_str},
                prompt_to_user="What should I remind you to do?"
            )
            return "What would you like me to remind you to do?", True

        # Otherwise user gave the reminder title/task
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
        # If user says "only once" while waiting for time, confirm and keep waiting for time
        if bool(re.match(r"^(?:only\s+once|one\s+time|just\s+once|once)[\.\?\!]*$", clean)):
            title = data.get("title", "Reminder")
            return f"Understood, one-time reminder for '{title}'. When should I remind you?", True

        # Got the time expression (e.g. "in 5 sec", "tomorrow at 9am", "in 10 minutes")
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

