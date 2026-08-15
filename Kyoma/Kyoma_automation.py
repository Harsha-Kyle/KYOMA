# Kyoma_automation_resilient.py
import platform
import subprocess
import win32com.client
import shlex
import json
import os
import traceback
import datetime
from datetime import datetime, timedelta
import dateparser
import re
import psutil
import time
import requests
from pathlib import Path
from shutil import which
import pyautogui
import pygetwindow as gw
from pywinauto import application
import getpass
from ollama import chat
from app_utils import resolve_lnk_target,open_with_exe,open_application,minimize_application,restore_application,close_application
from volume_control import set_volume, change_volume, mute_volume, unmute_volume, get_volume
from display_control import set_brightness,get_brightness,brightness_up,brightness_down,lock_screen
from media_control import play_pause, next_track, previous_track, startfrombegin_track, play
from system_info_utils import get_power_status, get_network_status, get_vpn_status, get_performance, get_disk_usage,get_time,get_date,get_battery,get_system_info
from reminder_utils import add_reminder, list_active_reminders, reminder_details, start_scheduler , cancel_reminder_by_title, add_birthday_reminder,list_birthday_reminders,delete_birthday_reminder
from screenshot import take_screenshot_save, clean_old_thumbs

# User-specific shortcuts (edit paths to match your system)
APP_SHORTCUTS = {
    "genshin impact": r"C:\Users\harsh\OneDrive\Desktop\Genshin Impact.lnk",
    "clash of clans": r"C:\Users\harsh\OneDrive\Desktop\Clash of Clans.lnk",
    "coc": r"C:\Users\harsh\OneDrive\Desktop\Clash of Clans.lnk",
    "valorant": r"C:\Users\Public\Desktop\VALORANT.lnk",
    "spotify": r"C:\Users\harsh\AppData\Roaming\Spotify\Spotify.exe",
    "discord": r"C:\Users\harsh\AppData\Local\Discord\app-1.0.9031\Discord.exe",
    "steam": r"C:\Program Files (x86)\Steam\steam.exe",
    "epic games": r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe",
    "roblox": r"C:\Users\harsh\AppData\Local\Roblox\Versions\RobloxPlayerLauncher.exe",
    "telegram": r"C:\Users\harsh\AppData\Roaming\Telegram Desktop\Telegram.exe",
    "speccy": r"C:\Users\Public\Desktop\Speccy.lnk"
    # add more exact app -> path mappings here
}

# Common "system" app map (name -> executable or heuristic)
SYSTEM_APPS = {
    "notepad": r"C:\Windows\System32\notepad.exe",
    "calculator": r"C:\Windows\System32\calc.exe",
    "calc": r"C:\Windows\System32\calc.exe",
    "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "chrome_x86": r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "explorer": r"C:\Windows\explorer.exe",
    "file explorer": r"C:\Windows\explorer.exe",
    "file manager": r"C:\Windows\explorer.exe",
    "files": r"C:\Windows\explorer.exe",
    "task manager": r"C:\Windows\System32\Taskmgr.exe",
    "paint": r"C:\Windows\System32\mspaint.exe",
    "snipping tool": r"C:\Windows\System32\SnippingTool.exe",
    "settings": r"C:\Windows\ImmersiveControlPanel\SystemSettings.exe",
    "control panel": r"C:\Windows\System32\control.exe",
    "run": r"C:\Windows\System32\RunDll32.exe",
    "system information": r"C:\Windows\System32\msinfo32.exe",
    "device manager": r"C:\Windows\System32\devmgmt.msc",
    "services": r"C:\Windows\System32\services.msc",
    "event viewer": r"C:\Windows\System32\eventvwr.msc",
    "registry editor": r"C:\Windows\regedit.exe",
    "wordpad": r"C:\Program Files\Windows NT\Accessories\wordpad.exe",
    "clock": r"C:\Windows\System32\time.exe",  # fallback placeholder
    "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "explorer.exe": r"C:\Windows\explorer.exe",
    # you can add more obvious binaries here
}



# --------------------
# CONFIG
# --------------------
OLLAMA_MODEL = "gemma4:e2b"
SYSTEM = platform.system().lower()

def _to_int_level(val, default=50):
    """Convert a level value to int, stripping '%' if present."""
    try:
        if isinstance(val, str):
            val = val.strip().rstrip('%')
        return int(float(val))
    except (ValueError, TypeError):
        return default


# --------------------
# STARTUP / OLLAMA
# --------------------
def ensure_ollama_running(model="kyoma"):
    try:
        requests.get("http://localhost:11434", timeout=2)
        print("✅ Ollama service already running.")
    except Exception:
        print("🚀 Starting Ollama service...")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True)
        if model not in r.stdout:
            print(f"📦 Pulling Ollama model '{model}'...")
            subprocess.run(["ollama", "pull", model])
        else:
            print(f"✅ Ollama model '{model}' available.")
    except Exception as e:
        print("⚠️ Ollama check failed:", e)

# --------------------
# UTILITIES (actions)
# --------------------


def open_browser(url="https://www.google.com"):
    try:
        if not url:
            url = "https://www.google.com"
        if not url.startswith("http"):
            url = "https://" + url
        chrome_exe = next((p for p in [SYSTEM_APPS.get("chrome"), SYSTEM_APPS.get("chrome_x86")] if p and os.path.exists(p)), None)
        if chrome_exe:
            subprocess.Popen([chrome_exe, url])
            return {"ok": True, "out": f"Opened Chrome with {url}"}
        subprocess.Popen(f'start "" "{url}"', shell=True)
        return {"ok": True, "out": f"Opened default browser with {url}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def web_search(query=""):
    """Search Google for a query and open results in Chrome."""
    try:
        if not query:
            return {"ok": False, "out": "Please provide a search query."}
        # Build Google search URL: spaces → +
        url = "https://www.google.com/search?q=" + "+".join(str(query).strip().split())
        chrome_exe = next((p for p in [SYSTEM_APPS.get("chrome"), SYSTEM_APPS.get("chrome_x86")] if p and os.path.exists(p)), None)
        if chrome_exe:
            subprocess.Popen([chrome_exe, url])
        else:
            subprocess.Popen(f'start "" "{url}"', shell=True)
        return {"ok": True, "out": f"Searching Google for: {query}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}  


# --------------------
# ACTION MAP
# --------------------
ACTION_MAP = {
    "get_time": {"fn": get_time},
    "get_date": {"fn": get_date},
    "get_battery": {"fn": get_battery},
    "get_system_info": {"fn": get_system_info},
    "screenshot": {"fn": lambda name=None, show=False, **kwargs: take_screenshot_save(name=name, show=show)},
    "ss": {"fn": lambda name=None, show=False, **kwargs: take_screenshot_save(name=name, show=show)},
    "open_application": {"fn": open_application},
    "open_browser": {"fn": open_browser},
    "web_search": {"fn": web_search},
    "minimize_application": {"fn": minimize_application},
    "restore_application": {"fn": restore_application},
    "close_application": {"fn": close_application},

    #volume control
    "set_volume": {"fn": lambda level=100: {"ok": True, "out": set_volume(_to_int_level(level, 100))}},
    "volume_up": {"fn": lambda: {"ok": True, "out": change_volume("up")}},
    "volume_down": {"fn": lambda: {"ok": True, "out": change_volume("down")}},
    "mute": {"fn": lambda: {"ok": True, "out": mute_volume()}},
    "unmute": {"fn": lambda: {"ok": True, "out": unmute_volume()}},
    "get_volume": {"fn": lambda: {"ok": True, "out": f"Current volume is {get_volume()}%" }},

    # Display / Screen actions
    "set_brightness": {"fn": lambda level=50: {"ok": True, "out": set_brightness(_to_int_level(level, 50))}},
    "get_brightness": {"fn": lambda: {"ok": True, "out": get_brightness()}},
    "brightness_up": {"fn": lambda: {"ok": True, "out": brightness_up()}},
    "brightness_down": {"fn": lambda: {"ok": True, "out": brightness_down()}},
    "lock_screen": {"fn": lambda: {"ok": True, "out": lock_screen()}},

    # Media key controls (Spotify, YouTube)
    "media_play": {"fn": play_pause},
    "media_play_pause": {"fn": play_pause},
    "media_next": {"fn": next_track},
    "media_prev": {"fn": previous_track},
    "media_begin": {"fn": startfrombegin_track},

    # system_info_utils
    "get_power_status": {"fn": lambda: {"ok": True, "out": get_power_status()}},
    "get_network_status": {"fn": lambda: {"ok": True, "out": get_network_status()}},
    "get_vpn_status": {"fn": lambda: {"ok": True, "out": get_vpn_status()}},
    "get_performance": {"fn": lambda: {"ok": True, "out": get_performance()}},
    "get_disk_usage": {"fn": lambda: {"ok": True, "out": get_disk_usage()}},

    #reminders
    "add_reminder": {"fn": lambda title="", message="", time="": {"ok": True, "out": add_reminder(title, message, time)}},
    "list_reminders": {"fn": list_active_reminders},
    "reminder_details": {"fn": lambda title="": reminder_details(title)},
    "cancel_reminder": {"fn": lambda title="": {"ok": True, "out": cancel_reminder_by_title(title)}},

    # birthdays
    "add_birthday_reminder": {"fn": lambda name="", date="": {"ok": True, "out": add_birthday_reminder(name, date)}},
    "list_birthday_reminders": {"fn": lambda: {"ok": True, "out": list_birthday_reminders()}},
    "delete_birthday_reminder": {"fn": lambda name="": {"ok": True, "out": delete_birthday_reminder(name)}},


    # keep this list authoritative
}

# --------------------
# Normalization / Validation
# --------------------
ACTION_ALIASES = {
    # action alias -> canonical
    "run_calc": "open_application",
    "run_calculator": "open_application",
    "open_app": "open_application",
    "open_application": "open_application",
    "open": "open_application",
    "open_program": "open_application",
    "get_response": "say",          # model sometimes emits this — handle as speak
    "status": "get_system_info",
    "speak": "say",
    "turn_off_screen": "lock_screen",
    "lock": "lock_screen",
    "lock_pc": "lock_screen",
    "screen_up": "brightness_up",
    "screen_down": "brightness_down",
    "play_pause": "media_play_pause",
    "play": "media_play_pause",
    "next": "media_next",
    "previous": "media_prev",
    "prev": "media_prev",
    "begin": "media_begin",
    "set_reminder": "add_reminder",
    "add_reminder": "add_reminder",
    "reminder": "add_reminder",
    "list_reminders": "list_reminders",
    "show_reminders": "list_reminders",
    "reminder_details": "reminder_details",
    "check_reminder": "reminder_details",
    "cancel_reminder": "cancel_reminder",
    "delete_reminder": "cancel_reminder",
    "remove_reminder": "cancel_reminder",
    "add_birthday": "add_birthday_reminder",
    "birthday_reminder": "add_birthday_reminder",
    "set_birthday": "add_birthday_reminder",
    "list_birthdays": "list_birthday_reminders",
    "show_birthdays": "list_birthday_reminders",
    "get_birthdays": "list_birthday_reminders",
    "delete_birthday": "delete_birthday_reminder",
    "remove_birthday": "delete_birthday_reminder",
    "cancel_birthday": "delete_birthday_reminder",
    "delete_birthday_reminder": "delete_birthday_reminder",
    "remove_birthday_reminder": "delete_birthday_reminder",

    # ── Alarm aliases → reminder equivalents ──────────────────────────
    "set_alarm": "add_reminder",
    "create_alarm": "add_reminder",
    "cancel_alarm": "cancel_reminder",
    "delete_alarm": "cancel_reminder",
    "list_alarms": "list_reminders",
    "show_alarms": "list_reminders",

    # ── Search aliases → web_search ───────────────────────────────────
    "search_google": "web_search",
    "google_search": "web_search",
    "search": "web_search",
    "web_search": "web_search",
    "search_web": "web_search",
    "search_for": "web_search",
    "look_up": "web_search",
    "lookup": "web_search",
    "find": "web_search",
    "browse": "open_browser",

    # ── Unsupported actions → polite say response ─────────────────────
    # These are hallucinated by the LLM but not implemented; silently
    # redirect to a 'say' that tells the user it's unsupported.
    "get_weather": "_unsupported",
    "convert_currency": "_unsupported",
    "translate_text": "_unsupported",
    "define_word": "_unsupported",
    "calculate": "_unsupported",
    "get_location": "_unsupported",
    "send_email": "_unsupported",
    "get_calendar_events": "_unsupported",
    "add_event_to_calendar": "_unsupported",
    "delete_event_from_calendar": "_unsupported",
    "list_events_in_calendar": "_unsupported",
    "get_stock_price": "_unsupported",
    "get_news": "_unsupported",
    "play_music": "_unsupported",
    "stop_music": "_unsupported",
    "get_contacts": "_unsupported",
    "call_contact": "_unsupported",
    "take_photo": "_unsupported",
    "record_video": "_unsupported",
}

# We'll implement a small 'say' action that just prints speak or args.text
def say_action(text=""):
    return {"ok": True, "out": text or ""}

# expand ACTION_MAP with 'say' to handle speak-only model outputs
ACTION_MAP["say"] = {"fn": say_action}

def canonicalize_action_json(raw):
    """
    Take raw parsed JSON (from model) and normalize:
    - canonical action name (via aliases)
    - canonical args keys: accept appName, app_name, name, app -> 'name'
    - ensure 'args' exists (dict)
    """
    if not isinstance(raw, dict):
        return None, "Parsed JSON is not an object."

    # copy to avoid mutating original
    data = dict(raw)

    # handle if model returned { "speak": "...", "args": {...} } w/o action
    if "action" not in data and "speak" in data and ("args" not in data or data.get("args")=={}):
        # treat as speak-only
        return {"action": "say", "args": {"text": data.get("speak","")}, "speak": data.get("speak","")}, None

    action = data.get("action")
    if not action:
        return None, "No 'action' field."

    # normalize action string (before alias lookup)
    action_raw = str(action).lower().strip()

    # ── Special case: any search action → web_search with query arg ─────────────
    _SEARCH_ACTIONS = ("search_google", "google_search", "web_search", "search",
                       "search_web", "search_for", "look_up", "lookup", "find")
    if action_raw in _SEARCH_ACTIONS:
        args = data.get("args") or {}
        query = (args.get("query") or args.get("q") or args.get("search_query") or
                 args.get("url") or args.get("text") or args.get("name") or "").strip()
        if query.startswith("http"):
            return {"action": "open_browser", "args": {"url": query}, "speak": data.get("speak")}, None
        return {"action": "web_search", "args": {"query": query}, "speak": data.get("speak")}, None

    # ── Lookup alias ──────────────────────────────────────────────────────
    action_norm = ACTION_ALIASES.get(action_raw, action_raw)

    # ── Unsupported action guard ──────────────────────────────────────────
    if action_norm == "_unsupported":
        return {"action": "say", "args": {"text": f"Sorry, I don't support '{action_raw}' yet. I can open apps, search the web, set reminders, control volume/brightness, and more."}, "speak": None}, None

    # prepare args
    args = data.get("args") or {}
    if not isinstance(args, dict):
        args = {}

    # normalize common arg keys to canonical ones:
    # appName, app_name, app, name -> 'name'
    canonical_args = {}
    for key in ["appName", "app_name", "name", "app"]:
        if key in args:
            canonical_args["name"] = args[key]
            break

    if "text" in args:
        canonical_args["text"] = args.get("text")
    # also accept top-level speak for say or to extract app name fallback
    if "name" not in canonical_args:
        # some models put the target in 'speak' or inside the 'speak' text
        sp = data.get("speak") or data.get("says") or ""
        # attempt to extract a probable app name (very heuristic: last two words)
        if sp:
            # simple heuristic: find known app names in speak
            lowered = sp.lower()
            for k in list(APP_SHORTCUTS.keys()) + list(SYSTEM_APPS.keys()) + ["spotify", "chrome", "notepad", "calculator", "calc", "genshin", "clash", "coc"]:
                if k in lowered:
                    canonical_args["name"] = k
                    break

    # preserve other args but don't rely on them for execution
    for k, v in args.items():
        if k not in ("appName", "app_name", "name", "app", "text"):
            canonical_args[k] = v

    normalized = {"action": action_norm, "args": canonical_args, "speak": data.get("speak")}
    return normalized, None

def validate_action_json(action_json):
    if not isinstance(action_json, dict):
        return False, "Action JSON must be an object."
    action = action_json.get("action")
    if not action or action not in ACTION_MAP:
        return False, f"Unknown or unsupported action '{action}'."
    return True, None

# --------------------
# Executor
# --------------------
def execute_action(action_json):
    try:
        normalized, err = canonicalize_action_json(action_json)
        if err:
            return {"ok": False, "error": f"Normalization failed: {err}"}
        valid, v_err = validate_action_json(normalized)
        if not valid:
            return {"ok": False, "error": v_err}
        
        # Handle say → built-in commands
        if normalized["action"] == "say" and "text" in normalized["args"]:
            text_lower = normalized["args"]["text"].lower()
            if "date" in text_lower:
                normalized["action"] = "get_date"
                normalized["args"] = {}
            elif "time is" in text_lower:
                normalized["action"] = "get_time"
                normalized["args"] = {}
            elif "battery" in text_lower:
                normalized["action"] = "get_battery"
                normalized["args"] = {}

        action = normalized["action"]
        args = normalized.get("args", {}) or {}

        # ✅ Handle birthday reminder creation
        if action == "add_birthday_reminder":
            name = args.get("name")
            date_str = args.get("date", "").strip()

            if not name or not date_str:
                return {
                    "ok": False,
                    "out": "Please specify both name and date, e.g. '05/11' or '5th November' for Kamal."
                }

            # 🔥 Natural language date parsing (like '5th November', 'Nov 5', etc.)
            parsed_date = dateparser.parse(
                date_str,
                settings={
                    'PREFER_DATES_FROM': 'future',
                    'DATE_ORDER': 'DMY'
                }
            )

            if not parsed_date:
                return {
                    "ok": False,
                    "out": f"⚠️ Couldn't understand the date '{date_str}'. Try formats like '5 November' or '05/11'."
                }

            day, month = parsed_date.day, parsed_date.month
            result = add_birthday_reminder(name, f"{day:02d}/{month:02d}")
            return {"ok": True, "out": result}


        # ✅ Handle reminder creation
        if action == "add_reminder":
            title = args.get("title", "Untitled Reminder")
            message = args.get("message", "")
            remind_time = (args.get("time") or args.get("in") or "").strip()

            now = datetime.now()
            remind_dt = None

            # 🔥 Use dateparser for natural language time
            parsed = dateparser.parse(remind_time, settings={'PREFER_DATES_FROM': 'future'})

            if parsed:
                remind_dt = parsed
            else:
                # ❌ Parsing failed — return error instead of fallback
                return {
                    "ok": False,
                    "out": f"⚠️ Failed to set reminder '{title}': couldn't parse time '{remind_time}'."
                }
            remind_str = remind_dt.strftime("%Y-%m-%d %H:%M:%S")
            recurrence = args.get("recurrence", None)

            result = add_reminder(title, message, remind_str, recurrence)
            return {"ok": True, "out": f"Reminder set for {remind_str}: {title}"}




        # ===== Execute the mapped function =====
        fn = ACTION_MAP[action]["fn"]

        try:
            result = fn(**normalized["args"]) if normalized.get("args") else fn()
        except TypeError:
            if "name" in normalized.get("args", {}):
                result = fn(normalized["args"]["name"])
            elif "text" in normalized.get("args", {}):
                result = fn(normalized["args"]["text"])
            else:
                result = fn()

        # Standardized output
        if isinstance(result, dict):
            return {"ok": result.get("ok", True), "out": result.get("out", "")}
        else:
            return {"ok": True, "out": str(result)}

    except Exception as e:
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}


# --------------------
# LLM / Ollama helpers
# --------------------

# --------------------
# LLM / Ollama helpers (Native Tool Calling)
# --------------------
from memory_manager import MemoryManager

# Define the tools we want the LLM to use
AVAILABLE_TOOLS = [
    get_time, get_date, get_battery, get_system_info,
    take_screenshot_save, open_application, open_browser, web_search,
    minimize_application, restore_application, close_application,
    set_volume, change_volume, mute_volume, unmute_volume, get_volume,
    set_brightness, get_brightness, brightness_up, brightness_down, lock_screen,
    play_pause, next_track, previous_track, startfrombegin_track,
    get_power_status, get_network_status, get_vpn_status, get_performance, get_disk_usage,
    add_reminder, list_active_reminders, reminder_details, cancel_reminder_by_title,
    add_birthday_reminder, list_birthday_reminders, delete_birthday_reminder
]

memory = MemoryManager(max_history=4)

def query_ollama_with_tools(user_text):
    memory.add_user_message(user_text)
    
    system_prompt = (
            "You are Kyoma, a PC automation assistant. "
            "Always call a tool for PC tasks — never say you can't. "
            "Reply short and direct."
    )
    
    try:
        # First round: user query
        resp = chat(
            model=OLLAMA_MODEL, 
            messages=memory.get_messages(system_prompt=system_prompt),
            tools=AVAILABLE_TOOLS
        )
        
        msg = resp["message"]
        
        # Check if the model wants to call tools
        if msg.get("tool_calls"):
            memory.add_assistant_message(tool_calls=msg["tool_calls"])
            
            # Execute all tools the model requested
            for tool_call in msg["tool_calls"]:
                func_name = tool_call["function"]["name"]
                args = tool_call["function"]["arguments"]
                
                print(f"🔧 Tool called: {func_name}({args})")
                
                # Find and execute the function
                result = "Function not found"
                for fn in AVAILABLE_TOOLS:
                    if fn.__name__ == func_name:
                        try:
                            res = fn(**args)
                            result = str(res) if res is not None else "Success"
                        except Exception as e:
                            result = f"Error executing {func_name}: {e}"
                        break
                
                memory.add_tool_message(text=result, name=func_name)
            
            # Second round: send tool results back to get final text response
            resp2 = chat(
                model=OLLAMA_MODEL,
                messages=memory.get_messages(system_prompt=system_prompt)
            )
            
            final_text = resp2["message"]["content"]
            memory.add_assistant_message(text=final_text)
            return {"ok": True, "text": final_text}
            
        else:
            # Model just responded with text
            text = msg.get("content", "")
            memory.add_assistant_message(text=text)
            return {"ok": True, "text": text}
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}

# --------------------
# REPL
# --------------------
def repl_loop():
    print("Kyoma ready. Type commands (say 'exit' to quit).")
    while True:
        try:
            user = input("You: ").strip()
            if not user:
                continue

            if user.lower() in ["exit", "quit", "bye", "clear memory"]:
                if user.lower() == "clear memory":
                    memory.clear()
                    print("Kyoma: Memory cleared.")
                    continue
                print("Kyoma: Goodbye.")
                break



            # Query Ollama using the new tool calling pipeline
            q = query_ollama_with_tools(user)
            if not q["ok"]:
                print("❌ Ollama error:", q["error"])
                continue
                
            print("Kyoma:", q["text"])
            print()

        except KeyboardInterrupt:
            print("\nKyoma: Interrupted. Goodbye.")
            break
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    ensure_ollama_running(OLLAMA_MODEL)

    # 🧹 Clean thumbnails on Kyoma startup
    clean_old_thumbs()

    # Start reminders scheduler
    start_scheduler()

    repl_loop()
