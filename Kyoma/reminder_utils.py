# hi
import sys
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
# reminder_utils_copy.py
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="win10toast_click")

import threading
import queue
import sqlite3
import ctypes
import datetime
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from apscheduler.schedulers.background import BackgroundScheduler
import re
import os
from win10toast_click import ToastNotifier
import dateparser  # ✅ new for better time parsing
from pathlib import Path


# Set custom Windows AppID so it doesn’t show "Python"
myappid = u'Kyoma.Assistant'
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

# Base directory
script_dir = Path(__file__).resolve().parent

# Create folder
reminder_folder = script_dir / "Reminders logs"
reminder_folder.mkdir(parents=True, exist_ok=True)

# Correct file paths (with Demo mode isolation support)
def get_db_path():
    try:
        from demo_safety import is_demo_mode_active
        if is_demo_mode_active():
            demo_db = reminder_folder / "reminders_demo.db"
            if not os.path.exists(demo_db):
                init_db(demo_db)
            return demo_db
    except Exception:
        pass
    return reminder_folder / "reminders.db"

class _DynamicDBPath:
    def __fspath__(self):
        return str(get_db_path())
    def __str__(self):
        return str(get_db_path())

DB_PATH = _DynamicDBPath()
LOG_PATH = reminder_folder / "reminder.log"

toaster = ToastNotifier()

_voice_input_instance = None
_tts_instance = None

def register_voice_services(voice_input=None, tts=None):
    """Register in-process voice_input and tts instances for safe coordination."""
    global _voice_input_instance, _tts_instance
    if voice_input is not None:
        _voice_input_instance = voice_input
    if tts is not None:
        _tts_instance = tts

def _is_reminder_voice_enabled() -> bool:
    """Check if 'reminder.speak_aloud' is enabled in settings.json or kyoma_config.json."""
    try:
        settings_file = Path(__file__).resolve().parent.parent / "backend" / "settings.json"
        if settings_file.exists():
            import json
            with open(settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "reminder.speak_aloud" in data:
                    return bool(data["reminder.speak_aloud"])
    except Exception:
        pass
    return True

# In-process thread-safe reminder queue coordinator
_reminder_speech_queue = queue.Queue()
_reminder_worker_running = False
_reminder_lock = threading.Lock()

def _reminder_playback_worker():
    import time
    import winsound
    import requests
    global _reminder_worker_running

    while True:
        try:
            text = _reminder_speech_queue.get(timeout=2.0)
        except queue.Empty:
            with _reminder_lock:
                _reminder_worker_running = False
                break

        # Wait if KYOMA is currently thinking or speaking
        while True:
            is_busy = False
            if _voice_input_instance is not None:
                if getattr(_voice_input_instance, "system_state", "IDLE") in ("THINKING", "SPEAKING"):
                    is_busy = True
            if not is_busy:
                break
            time.sleep(0.5)

        # 1. Mute microphone before reminder playback
        if _voice_input_instance is not None:
            try:
                _voice_input_instance.mute()
            except Exception:
                pass
        else:
            try:
                requests.post("http://localhost:8000/api/record/mute", timeout=0.5)
            except Exception:
                pass

        # 2. Synthesize audio via in-process TTS or HTTP fallback
        audio_bytes = None
        if _tts_instance is not None:
            try:
                audio_bytes = _tts_instance.synthesize(text)
            except Exception as e:
                log_event(f"⚠️ [Reminder TTS Direct Error] {e}")

        if not audio_bytes:
            try:
                resp = requests.post(
                    "http://localhost:8000/api/tts",
                    json={"text": text},
                    timeout=5.0
                )
                if resp.status_code == 200 and resp.content:
                    audio_bytes = resp.content
            except Exception as e:
                log_event(f"⚠️ [Reminder TTS HTTP Error] {e}")

        # 3. Play audio
        if audio_bytes:
            try:
                winsound.PlaySound(audio_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except Exception as e:
                log_event(f"⚠️ [Reminder PlaySound Error] {e}")

        # 4. Unmute microphone and restore appropriate standby state based on input mode
        if _voice_input_instance is not None:
            try:
                _voice_input_instance.unmute()
                if getattr(_voice_input_instance, "input_mode", "wake_word") == "always_listening":
                    _voice_input_instance.system_state = "LISTENING"
                else:
                    _voice_input_instance.system_state = "IDLE"
            except Exception:
                pass
        else:
            try:
                requests.post("http://localhost:8000/api/record/unmute", timeout=0.5)
            except Exception:
                pass

        _reminder_speech_queue.task_done()

def _speak_reminder(text: str):
    """
    Queue reminder speech for playback. Checks 'reminder.speak_aloud' setting,
    waits for LLM/TTS to finish, mutes the microphone in-process, plays audio,
    and returns to idle/wake-word standby cleanly.
    """
    if not _is_reminder_voice_enabled():
        log_event(f"ℹ️ [Reminder Voice Skipped] 'reminder.speak_aloud' is disabled: '{text}'")
        return

    global _reminder_worker_running
    _reminder_speech_queue.put(text)
    with _reminder_lock:
        if not _reminder_worker_running:
            _reminder_worker_running = True
            threading.Thread(target=_reminder_playback_worker, daemon=True).start()

# ----------------------
# LOGGING
# ----------------------
log_lock = threading.Lock()

def log_event(event):
    """Append an event to the reminder log file with timestamp."""
    with log_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {event}\n")

# ----------------------
# DATABASE SETUP
# ----------------------
def init_db(target_path=None):
    db_file = target_path or get_db_path()
    if not os.path.exists(db_file):
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                message TEXT,
                time TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                repeat_interval TEXT DEFAULT NULL
            )
        """)
        conn.commit()
        conn.close()

init_db()

# ----------------------
# TIME UTILITIES
# ----------------------
def normalize_datetime(dt_str):
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
    match = re.match(r"(\d+)\s*(sec|secs|second|seconds|min|mins|minute|minutes|hour|hours|hr|hrs|day|days)", time_str)
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
    return datetime.now() + delta

# ----------------------
# DATABASE FUNCTIONS
# ----------------------
def add_reminder(title: str, message: str, remind_time: str, recurrence: str = None):
    """
    Add a new reminder to the database and schedule it.

    Args:
        title: Short name for the reminder (e.g. "Drink water", "Call mom").
        message: Optional longer description shown in the notification.
        remind_time: When to fire the reminder. Accepts natural language like:
            - "in 10 minutes", "in 1 hour", "in 30 seconds"
            - "tomorrow at 9am", "tonight at 8pm"
            - "2026-08-15 14:30:00" (absolute datetime)
            ALWAYS pass the user's exact time phrase — do NOT say time is missing if the user
            said things like "in 1 min", "in 5 minutes", "after 2 hours", etc.
        recurrence: How often to repeat. Options: "daily", "weekly", "monthly", "yearly",
            "every 2 days", "every 3 weeks". Leave as None for a one-time reminder.
            IMPORTANT: If the user does not explicitly ask for a repeating reminder, leave recurrence as None.
    """
    if recurrence is None:
        recurrence = "one time"
    # Prevent context contamination: if message is empty, whitespace, or looks like conversation residue, default to title
    clean_title = (title or "").strip()
    clean_msg = (message or "").strip()
    if not clean_msg or clean_msg == clean_title:
        clean_msg = clean_title

    remind_dt = None
    try:
        remind_dt = datetime.strptime(normalize_datetime(remind_time), "%Y-%m-%d %H:%M:%S")
    except Exception:
        remind_dt = parse_relative_time(remind_time)

    if not remind_dt:
        remind_dt = datetime.now() + timedelta(minutes=1)

    normalized_time = remind_dt.strftime("%Y-%m-%d %H:%M:%S")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO reminders (title, message, time, status, repeat_interval) VALUES (?, ?, ?, ?, ?)",
        (clean_title, clean_msg, normalized_time, "pending", recurrence)
    )
    conn.commit()
    reminder_id = c.lastrowid
    conn.close()

    reminder = {
        "id": reminder_id,
        "title": clean_title,
        "message": clean_msg,
        "time": normalized_time,
        "repeat_interval": recurrence if recurrence else None
    }

    schedule_reminder(reminder)
    log_event(f"🗓️ [Scheduled              ] reminder : '{title}' at {normalized_time} (recurrence: {recurrence})")
    return reminder

def get_active_reminders():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        SELECT id, title, message, time, repeat_interval 
        FROM reminders 
        WHERE status='pending'
    """)
    rows = c.fetchall()
    conn.close()
    return [
        {"id": r[0], "title": r[1], "message": r[2], "time": r[3], "repeat_interval": r[4]} 
        for r in rows
    ]

def mark_reminder_completed(reminder_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET status='completed' WHERE id=?", (reminder_id,))
    conn.commit()
    conn.close()

def reminder_details(title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, title, message, time, status, repeat_interval FROM reminders WHERE title LIKE ?",
        (f"%{title}%",)
    )
    row = c.fetchone()
    conn.close()
    if row:
        recurrence = row[5] if row[5] else "None"
        return f"Reminder '{row[1]}' at {row[3]} - {row[2]} (Status: {row[4]}, Recurrence: {recurrence})"
    return f"No reminder found for '{title}'"

def get_reminder_by_id(reminder_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, title, message, time, repeat_interval FROM reminders WHERE id=?", (reminder_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "title": row[1], "message": row[2], "time": row[3], "repeat_interval": row[4]}
    return None

# ----------------------
# NOTIFICATION HANDLING
# ----------------------
def show_toast(title, message, callback=None):
    try:
        toaster.show_toast(
            title=title,
            msg=message,
            icon_path=None,
            duration=10,
            threaded=True,
            callback_on_click=callback
        )
    except Exception as e:
        log_event(f"⚠️ [Toast Error            ] failed to show toast: {e}")
        print(f"⚠️ Toast notification error: {e}")

def trigger_reminder(title, message, reminder_id, repeat_interval=None):
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
        print(f"⚠️ Toast error for reminder '{title}': {e}")

    # Retry/snooze logic if not clicked within 60 seconds
    def retry_check():
        if not clicked["done"]:
            log_event(f"⏱️ [Snoozed                ] reminder : '{title}' for 5 minutes")
            scheduler.add_job(
                trigger_reminder,
                'date',
                run_date=datetime.now() + timedelta(minutes=5),
                args=[title, message, reminder_id, repeat_interval]
            )
    scheduler.add_job(retry_check, 'date', run_date=datetime.now() + timedelta(seconds=60))

def trigger_missed_reminder(title, message, reminder_id):
    reminder = get_reminder_by_id(reminder_id)
    repeat_interval = reminder.get("repeat_interval") if reminder else None
    clicked = {"done": False}

    def on_click():
        clicked["done"] = True
        log_event(f"🛎️ [Missed Acknowledged    ] reminder : '{title}'")
        if repeat_interval and repeat_interval.lower() not in ["one time", "one-time", "none", ""]:
            schedule_next_occurrence(reminder_id, title, message, repeat_interval)
        else:
            mark_reminder_completed(reminder_id)
        return 0

    _speak_reminder(f"You missed a reminder: {title}.")
    show_toast(f"Missed Reminder: {title}", f"{message}\n⏰ You missed it!", callback=on_click)
    log_event(f"⚠️ [Missed                 ] reminder : '{title}' - retry scheduled in 5 minutes")

    def retry_check():
        if not clicked["done"]:
            log_event(f"🚨 [Missed Not Acknowledged] reminder : '{title}' - retry scheduled in 5 minutes")
            scheduler.add_job(
                trigger_reminder,
                'date',
                run_date=datetime.now() + timedelta(minutes=5),
                args=[title, message, reminder_id, repeat_interval]
            )
    scheduler.add_job(retry_check, 'date', run_date=datetime.now() + timedelta(seconds=60))

def schedule_next_occurrence(reminder_id, title, message, repeat_interval):
    reminder = get_reminder_by_id(reminder_id)
    if not reminder:
        return

    try:
        last_time = datetime.strptime(normalize_datetime(reminder["time"]), "%Y-%m-%d %H:%M:%S")
    except Exception:
        last_time = datetime.now()

    interval = (repeat_interval or "").lower()
    next_time = None

    # Standard recurrences
    if interval == "daily":
        next_time = last_time + timedelta(days=1)
    elif interval == "weekly":
        next_time = last_time + timedelta(weeks=1)
    elif interval == "monthly":
        next_time = last_time + relativedelta(months=1)
    elif interval == "yearly":
        next_time = last_time + relativedelta(years=1)


    # Flexible: e.g. "every 2 days", "every 3 weeks"
    elif interval.startswith("every "):
        parts = interval.split()   
        if len(parts) == 3 and parts[0] == "every":
            try:
                n = int(parts[1])
                unit = parts[2]
                if "day" in unit:
                    next_time = last_time + timedelta(days=n)
                elif "week" in unit:
                    next_time = last_time + timedelta(weeks=n)
                elif "month" in unit:
                    next_time = last_time + relativedelta(months=n)
                elif "year" in unit:
                    next_time = last_time + relativedelta(years=n)
            except Exception:
                pass


    # Fall back to relative time parser if defined
    if not next_time:
        next_time = parse_relative_time(repeat_interval)


    if not next_time:
        log_event(f"⚠️ [Recurrence Error       ] invalid recurrence for '{title}' → {repeat_interval}")
        return                                 


    # 🩵 Ensure the next time is always in the future
    while next_time <= datetime.now():
        if "day" in interval:
            next_time += timedelta(days=1)
        elif "week" in interval:
            next_time += timedelta(weeks=1)
        elif "month" in interval:
            next_time += relativedelta(months=1)
        elif "year" in interval:
            next_time += relativedelta(years=1)
        else:
            next_time += timedelta(days=1)


    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "UPDATE reminders SET time=?, status='pending' WHERE id=?",
        (next_time.strftime("%Y-%m-%d %H:%M:%S"), reminder_id)
    )
    conn.commit()
    conn.close()

    schedule_reminder({
        "id": reminder_id,
        "title": title,
        "message": message,
        "time": next_time.strftime("%Y-%m-%d %H:%M:%S"),
        "repeat_interval": repeat_interval
    })

    log_event(f"🔁 [Next Occurrence        ] scheduled: '{title}' at {next_time.strftime('%Y-%m-%d %H:%M:%S')}")

def snooze_reminder(reminder_id, minutes=5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    new_time = datetime.now() + timedelta(minutes=minutes)
    c.execute("UPDATE reminders SET time=?, status='pending' WHERE id=?", (new_time.strftime("%Y-%m-%d %H:%M:%S"), reminder_id))
    conn.commit()
    conn.close()
    reminder = get_reminder_by_id(reminder_id)
    schedule_reminder(reminder)
    log_event(f"⏱️ [Snoozed                ] reminder : '{reminder['title']}' for {minutes} minutes")

def cancel_reminder_by_title(title):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT id, time, repeat_interval, status
        FROM reminders
        WHERE LOWER(title)=LOWER(?)
          AND (status='pending' OR (repeat_interval IS NOT NULL AND repeat_interval != ''))
    """, (title,))
    results = c.fetchall()

    if not results:
        log_event(f"⚠️ [Cancel Failed          ] no active reminder found with title '{title}'")
        conn.close()
        return

    cancelled_count = 0

    for reminder_id, time, recurrence, status in results:
        c.execute("UPDATE reminders SET status='cancelled' WHERE id=?", (reminder_id,))
        cancelled_count += 1

        for job in scheduler.get_jobs():
            if len(job.args) >= 3 and job.args[2] == reminder_id:
                scheduler.remove_job(job.id)
                log_event(f"🧹 [Scheduler Job Removed  ] reminder : '{title}' (ID {reminder_id})")

        log_event(
            f"🛑 [Cancelled              ] reminder : '{title}' (ID {reminder_id}, time {time}, recurrence: {recurrence or 'none'})"
        )

    conn.commit()
    conn.close()

    if cancelled_count > 1:
        log_event(f"🧹 [Bulk Cancelled         ] {cancelled_count} active reminders titled '{title}'")
    else:
        log_event(f"✅ [Cancelled One          ] reminder titled '{title}'")

# ----------------------
# SCHEDULER
# ----------------------
# MISSED REMINDER POLICY:
# When KYOMA starts, load_and_schedule_all() finds pending reminders whose time has passed.
# These are fired as staggered "missed" notifications (15s apart) with a special toast.
# If the user does not acknowledge within 60s, they are snoozed for 5 minutes.
# One-time reminders are marked completed after acknowledgment.
# Recurring reminders schedule their next occurrence.
scheduler = BackgroundScheduler(daemon=True)

def schedule_reminder(reminder, stagger_index=None):
    reminder_id = reminder["id"]
    title = reminder["title"]
    message = reminder["message"]
    remind_at = reminder["time"]
    repeat_interval = reminder.get("repeat_interval")

    # Use strptime directly to avoid re-parsing through dateparser (which can misinterpret already-formatted strings)
    try:
        remind_time = datetime.strptime(remind_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        # Fallback: try normalize_datetime if the format is unexpected
        try:
            remind_time = datetime.strptime(normalize_datetime(remind_at), "%Y-%m-%d %H:%M:%S")
        except Exception:
            print(f"⚠️ Skipping invalid reminder datetime for: {title} (value: {remind_at})")
            log_event(f"⚠️ [Invalid DateTime       ] skipped reminder '{title}' — bad time: {remind_at}")
            return

    now = datetime.now()
    if remind_time <= now:
        # If the reminder is older than 15 minutes, mark it missed/expired silently without firing audible alarm bursts
        overdue_seconds = (now - remind_time).total_seconds()
        if overdue_seconds > 900:  # > 15 minutes
            mark_reminder_completed(reminder_id)
            log_event(f"ℹ️ [Stale Reminder Auto-Cleared] '{title}' was {overdue_seconds/60:.1f} mins overdue — marked completed.")
            print(f"ℹ️ Auto-cleared stale reminder '{title}' ({overdue_seconds/60:.1f} mins overdue)")
            return

        if stagger_index is not None:
            delay_seconds = 15
            run_date = now + timedelta(seconds=delay_seconds * stagger_index)
        else:
            run_date = now
        print(f"⚠️ Missed reminder '{title}' — was scheduled at {remind_at}, firing missed notification.")
        scheduler.add_job(trigger_missed_reminder, 'date', run_date=run_date, args=[title, message, reminder_id])
        return

    print(f"✅ Scheduled reminder '{title}' at {remind_at}")
    scheduler.add_job(trigger_reminder, 'date', run_date=remind_time, args=[title, message, reminder_id, repeat_interval])

def load_and_schedule_all():
    missed_idx = 0
    for r in get_active_reminders():
        try:
            remind_time = datetime.strptime(normalize_datetime(r["time"]), "%Y-%m-%d %H:%M:%S")
        except Exception:
            mark_reminder_completed(r["id"])
            continue

        if remind_time <= datetime.now():
            schedule_reminder(r, stagger_index=missed_idx)
            missed_idx += 1
        else:
            schedule_reminder(r)

def start_scheduler():
    if getattr(scheduler, "running", False):
        return
    scheduler.start()
    print("✅ Reminder scheduler started")
    load_and_schedule_all()

start_scheduler()

# ----------------------
# HELPER
# ----------------------
def _format_natural_time(time_str: str) -> str:
    """Convert an ISO/standard datetime string into natural speech like 'today at 2:30 PM'."""
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return time_str

    now = datetime.now()
    time_part = dt.strftime("%I:%M %p").lstrip("0")
    if dt.date() == now.date():
        return f"today at {time_part}"
    elif dt.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {time_part}"
    else:
        return f"on {dt.strftime('%B')} {dt.day} at {time_part}"


def reset_demo_reminders() -> str:
    """Reset the demo reminders database. Only allowed in demo mode and never touches production DB."""
    try:
        from demo_safety import is_demo_mode_active
        if not is_demo_mode_active():
            return "Demo reset is only available when demo mode is active."
    except Exception:
        return "Demo mode check failed."

    demo_db = reminder_folder / "reminders_demo.db"
    if os.path.exists(demo_db):
        try:
            conn = sqlite3.connect(demo_db)
            c = conn.cursor()
            c.execute("DELETE FROM reminders")
            conn.commit()
            conn.close()
            log_event("🧹 [Demo Reset] Cleared all reminders from reminders_demo.db")
            return "Demo reminders database has been reset."
        except Exception as e:
            return f"Error resetting demo database: {e}"
    return "Demo database does not exist yet."


def list_active_reminders():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(get_db_path())
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, message, time, repeat_interval, status
        FROM reminders
        WHERE status = 'pending' AND datetime(time) > datetime(?)
        ORDER BY datetime(time) ASC
    """, (now_str,))

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "You have no upcoming reminders scheduled."

    total_count = len(rows)

    # Deduplicate identical titles while preserving order
    seen_titles = {}
    ordered_unique = []
    for row in rows:
        title = re.sub(r'[\U00010000-\U0010ffff\u2600-\u26ff\u2700-\u27bf🎉🎂🔔]+', '', row[1]).strip()
        time_nat = _format_natural_time(row[3])
        if title not in seen_titles:
            seen_titles[title] = 1
            ordered_unique.append((title, time_nat))
        else:
            seen_titles[title] += 1

    spoken_items = []
    for title, time_nat in ordered_unique[:3]:
        count = seen_titles[title]
        dup_note = f" (and {count - 1} more)" if count > 1 else ""
        spoken_items.append(f"{title}{dup_note} {time_nat}")

    if len(spoken_items) == 1:
        details = spoken_items[0]
    elif len(spoken_items) == 2:
        details = f"{spoken_items[0]}, and {spoken_items[1]}"
    else:
        details = ", ".join(spoken_items[:-1]) + f", and {spoken_items[-1]}"

    return f"You have {total_count} upcoming reminder{'s' if total_count != 1 else ''}: {details}."




# ----------------------
# BIRTHDAY REMINDERS
# ----------------------
def add_birthday_reminder(name, date_str):
    """
    Create two yearly recurring reminders:
    - One for the birthday day (00:00)
    - One the previous day at 09:00 AM saying "Tomorrow is X's Birthday"
    Example input: add_birthday_reminder("Kamal", "05/11")
    """
    try:
        day, month = map(int, date_str.split("/"))
        year = datetime.now().year

        # Base birthday date this year
        birthday_this_year = datetime(year, month, day, 0, 0)

        # If this year's birthday already passed, move to next year
        if birthday_this_year < datetime.now():
            birthday_this_year += relativedelta(years=1)

        # --- Main Birthday ---
        birthday_time = birthday_this_year.strftime("%Y-%m-%d %H:%M:%S")
        title = f"{name}'s Birthday 🎉"
        message = f"Wish {name} a happy birthday today!"
        add_reminder(title, message, birthday_time, recurrence="yearly")

        # --- Previous Day Reminder ---
        prev_day = birthday_this_year - timedelta(days=1)
        prev_day_time = prev_day.replace(hour=9, minute=0, second=0)
        prev_title = f"Tomorrow is {name}'s Birthday 🎂"
        prev_message = f"Reminder: {name}'s birthday is tomorrow!"
        add_reminder(prev_title, prev_message, prev_day_time.strftime("%Y-%m-%d %H:%M:%S"), recurrence="yearly")

        return (
            f"✅ Birthday reminders set for {name}:\n"
            f" - {day:02d}/{month:02d} 🎉 (main day)\n"
            f" - {prev_day.strftime('%d/%m')} 🎂 (previous day 9 AM)"
        )

    except Exception as e:
        return f"⚠️ Error creating birthday reminder: {e}"




def list_birthday_reminders():
    """List only real birthday reminders (ignore 'Tomorrow' ones)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, title, message, time, repeat_interval, status
        FROM reminders
        WHERE (repeat_interval = 'yearly' OR title LIKE '%Birthday%')
        AND title NOT LIKE '%Tomorrow%'
        AND status = 'pending'
        ORDER BY datetime(time) ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return "🎂 No upcoming birthdays found."

    lines = ["🎉 Upcoming Birthday Reminders:\n"]
    for row in rows:
        rid, title, msg, time_str, recurrence, status = row
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
            formatted_time = dt.strftime("%d %b %Y, %I:%M %p")
            lines.append(f"🗓️ {title} — {formatted_time} ({recurrence})")
        except Exception:
            lines.append(f"🗓️ {title} — {time_str} ({recurrence})")

    return "\n".join(lines)

def delete_birthday_reminder(name):
    """
    Delete both the main birthday and the previous-day reminder for the given person.
    Example: delete_birthday_reminder("Kamal")
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Find all matching reminders (main + previous day)
    c.execute("""
        SELECT id, title, time, status
        FROM reminders
        WHERE REPLACE(title, '🎉', '') LIKE ? OR REPLACE(title, '🎂', '') LIKE ?
        """, (f"%{name}%", f"%{name}%"))


    rows = c.fetchall()

    if not rows:
        conn.close()
        return f"⚠️ No birthday reminders found for '{name}'."

    deleted_count = 0

    for rid, title, time, status in rows:
        c.execute("DELETE FROM reminders WHERE id=?", (rid,))
        deleted_count += 1

        # Also remove any scheduled jobs
        for job in scheduler.get_jobs():
            if len(job.args) >= 3 and job.args[2] == rid:
                scheduler.remove_job(job.id)
                log_event(f"🧹 [Scheduler Job Removed  ] birthday reminder: '{title}'")

        log_event(f"🗑️ [Deleted Birthday        ] reminder : '{title}' at {time} (Status: {status})")

    conn.commit()
    conn.close()

    return f"✅ Deleted {deleted_count} birthday reminder(s) for '{name}'."
