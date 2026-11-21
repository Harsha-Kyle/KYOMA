import re

with open("Kyoma/reminder_utils.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update parse_relative_time and normalize_datetime
old_parse = '''def normalize_datetime(dt_str):
    """Normalize various datetime string formats into '%Y-%m-%d %H:%M:%S'."""
    if not dt_str:
        raise ValueError("Empty datetime string")

    # Try to parse with dateparser first (handles natural language)
    parsed = dateparser.parse(dt_str, settings={'PREFER_DATES_FROM': 'future'})
    if parsed:
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    # fallback to manual formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized datetime format: {dt_str}")

def parse_relative_time(time_str):
    """Parse relative time strings like 'in 10 minutes', '2 hours', etc."""
    if not time_str:
        return None
    parsed = dateparser.parse(time_str, settings={'PREFER_DATES_FROM': 'future'})
    if parsed:
        return parsed

    # fallback regex if still not parsed
    time_str = time_str.lower().strip()
    match = re.match(r"(\\d+)\\s*(sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|hr|hrs|day|days)", time_str)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    if "sec" in unit:
        delta = timedelta(seconds=amount)
    elif "min" in unit:
        delta = timedelta(minutes=amount)
    elif "hour" in unit or "hr" in unit:
        delta = timedelta(hours=amount)
    elif "day" in unit:
        delta = timedelta(days=amount)
    else:
        return None
    return datetime.now() + delta'''

new_parse = '''def normalize_datetime(dt_str):
    """Normalize various datetime string formats into '%Y-%m-%d %H:%M:%S'."""
    if not dt_str:
        raise ValueError("Empty datetime string")

    cleaned = dt_str.strip()
    # Normalize common STT anomalies like 'and 1 minute', 'in 1 min'
    cleaned = re.sub(r"^(?:and|after)\\s+", "in ", cleaned, flags=re.IGNORECASE)

    # Try to parse with dateparser first (handles natural language)
    parsed = dateparser.parse(cleaned, settings={'PREFER_DATES_FROM': 'future'})
    if parsed:
        # If time is in the past for today, advance by 1 day
        now = datetime.now()
        if parsed <= now and (now - parsed).total_seconds() > 60:
            # User specified a clock time that already passed today (e.g. 8 PM at 10 PM)
            parsed += timedelta(days=1)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    # fallback to manual formats
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M"
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            now = datetime.now()
            if dt <= now and (now - dt).total_seconds() > 60:
                dt += timedelta(days=1)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    raise ValueError(f"Unrecognized datetime format: {dt_str}")

def parse_relative_time(time_str):
    """Parse relative time strings like 'in 10 minutes', 'and 1 minute', '2 hours', etc."""
    if not time_str:
        return None
    cleaned = time_str.strip()
    cleaned = re.sub(r"^(?:and|after)\\s+", "in ", cleaned, flags=re.IGNORECASE)
    parsed = dateparser.parse(cleaned, settings={'PREFER_DATES_FROM': 'future'})
    if parsed:
        return parsed

    # fallback regex if still not parsed
    cleaned_lower = cleaned.lower().strip()
    match = re.match(r"(?:in\\s+)?(\\d+)\\s*(sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|hr|hrs|day|days)", cleaned_lower)
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2)
    if "sec" in unit:
        delta = timedelta(seconds=amount)
    elif "min" in unit:
        delta = timedelta(minutes=amount)
    elif "hour" in unit or "hr" in unit:
        delta = timedelta(hours=amount)
    elif "day" in unit:
        delta = timedelta(days=amount)
    else:
        return None
    return datetime.now() + delta'''

assert old_parse in content, "old_parse not found"
content = content.replace(old_parse, new_parse)

# 2. Update add_reminder return and handling
old_add_rem = '''    schedule_reminder(reminder)
    log_event(f"🗓️ [Scheduled              ] reminder : '{title}' at {normalized_time} (recurrence: {recurrence})")
    return reminder'''

new_add_rem = '''    schedule_reminder(reminder)
    log_event(f"🗓️ [Scheduled              ] reminder : '{clean_title}' at {normalized_time} (recurrence: {recurrence})")
    return _format_reminder_response(clean_title, normalized_time, recurrence)'''

assert old_add_rem in content, "old_add_rem not found"
content = content.replace(old_add_rem, new_add_rem)

# 3. Update trigger_reminder atomic DB state update & winotify toast
old_trigger = '''def trigger_reminder(title, message, reminder_id, repeat_interval=None):
    clicked = {"done": False}

    def on_click():
        clicked["done"] = True
        log_event(f"✅ [Acknowledged           ] reminder : '{title}'")
        if repeat_interval and repeat_interval.lower() not in ["one time", "one-time", "none", ""]:
            schedule_next_occurrence(reminder_id, title, message, repeat_interval)
        else:
            mark_reminder_completed(reminder_id)
        return 0

    log_event(f"🔔 [Triggered              ] reminder : '{title}' - {message} at {datetime.now().strftime('%H:%M:%S')}")
    print(f"🔔 Reminder firing: '{title}' — {message}")

    # Deliver reminder via spoken TTS audio with mic-mute protection
    spoken_text = f"Reminder: {title}. {message}" if message and message != title else f"Reminder: {title}."
    _speak_reminder(spoken_text)

    # Show the reminder toast
    try:
        toaster.show_toast(
            f"Reminder: {title}",
            message or "Reminder!",
            icon_path=None,
            duration=10,
            threaded=True,
            callback_on_click=on_click
        )
    except Exception as e:
        log_event(f"⚠️ [Toast Error            ] trigger_reminder failed for '{title}': {e}")
        print(f"⚠️ Toast error for reminder '{title}': {e}")'''

new_trigger = '''def trigger_reminder(title, message, reminder_id, repeat_interval=None):
    # Atomic transition: only ONE worker can claim and fire a pending reminder
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET status='fired' WHERE id=? AND status='pending'", (reminder_id,))
    if c.rowcount == 0:
        conn.close()
        return  # Already claimed or cancelled
    conn.commit()
    conn.close()

    clicked = {"done": False}

    def on_click():
        clicked["done"] = True
        log_event(f"✅ [Acknowledged           ] reminder : '{title}'")
        if repeat_interval and repeat_interval.lower() not in ["one time", "one-time", "none", ""]:
            schedule_next_occurrence(reminder_id, title, message, repeat_interval)
        else:
            mark_reminder_completed(reminder_id)
        return 0

    log_event(f"🔔 [Triggered              ] reminder : '{title}' - {message} at {datetime.now().strftime('%H:%M:%S')}")
    print(f"🔔 Reminder firing: '{title}' — {message}")

    # Deliver reminder via spoken TTS audio with mic-mute protection
    spoken_text = f"Reminder: {title}. {message}" if message and message != title else f"Reminder: {title}."
    _speak_reminder(spoken_text)

    # Show the reminder toast via winotify (native Windows action center) with win10toast fallback
    toast_shown = False
    try:
        from winotify import Notification, audio
        toast = Notification(
            app_id="Kyoma.Assistant",
            title=f"Reminder: {title}",
            msg=message or "Reminder!",
            duration="short"
        )
        toast.set_audio(audio.Default, loop=False)
        toast.show()
        toast_shown = True
    except Exception as notif_err:
        log_event(f"⚠️ [Winotify Error         ] {notif_err}")

    if not toast_shown:
        try:
            toaster.show_toast(
                f"Reminder: {title}",
                message or "Reminder!",
                icon_path=None,
                duration=10,
                threaded=False
            )
        except Exception as e:
            log_event(f"⚠️ [Toast Fallback Error   ] {e}")'''

assert old_trigger in content, "old_trigger not found"
content = content.replace(old_trigger, new_trigger)

# 4. Make start_scheduler strictly idempotent
old_start = '''def start_scheduler():
    if getattr(scheduler, "running", False):
        return
    scheduler.start()
    print("✅ Reminder scheduler started")
    load_and_schedule_all()'''

new_start = '''_scheduler_initialized = False

def start_scheduler():
    global _scheduler_initialized
    if _scheduler_initialized or getattr(scheduler, "running", False):
        return
    _scheduler_initialized = True
    scheduler.start()
    print("✅ Reminder scheduler started")
    load_and_schedule_all()'''

assert old_start in content, "old_start not found"
content = content.replace(old_start, new_start)

with open("Kyoma/reminder_utils.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Kyoma/reminder_utils.py updated successfully!")
