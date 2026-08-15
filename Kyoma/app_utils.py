# app_utils.py

import subprocess
import win32com.client
import shlex
import os
from datetime import datetime, timedelta
import time
from pathlib import Path
from shutil import which
import pygetwindow as gw
from pywinauto import application
from ollama import chat


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


def resolve_lnk_target(lnk_path):
    """Return target path, arguments, and working directory of .lnk file using Windows Shell."""
    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(lnk_path)
        return {
            "target": shortcut.TargetPath,
            "arguments": shortcut.Arguments,
            "working_dir": shortcut.WorkingDirectory
        }
    except Exception:
        return None


def open_with_exe(exe_path, args=None, mode="normal"):
    """Open executable or .lnk and optionally minimize/maximize window."""
    try:
        args = args or []
        
        working_dir = None

        # resolve shortcut target

        # resolve shortcut target
        if exe_path.lower().endswith(".lnk"):
            try:
                shell = win32com.client.Dispatch("WScript.Shell")
                shortcut = shell.CreateShortcut(exe_path)
                target = shortcut.TargetPath
                if target and os.path.exists(target):
                    exe_path = target
                    working_dir = os.path.dirname(target)
                else:
                    # fallback for UWP / store apps: let Windows handle the shortcut
                    os.startfile(exe_path)
                    return {"ok": True, "out": f"Opened shortcut {exe_path} via Windows"}
            except Exception:
                # fallback if win32com fails: let Windows handle it
                os.startfile(exe_path)
                return {"ok": True, "out": f"Opened shortcut {exe_path} via Windows"}


        si = subprocess.STARTUPINFO()
        if mode == "maximized":
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 3

        subprocess.Popen([exe_path] + args, startupinfo=si)

        if mode == "minimized":
            # give the window a moment to appear
            time.sleep(1)
            try:
                for w in gw.getAllWindows():
                    if exe_path.split("\\")[-1].split(".")[0].lower() in w.title.lower():
                        w.minimize()
                        break
            except Exception:
                pass



        return {"ok": True, "out": f"Opened {exe_path} ({mode})"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def open_application(name, state="normal"):
    """Open an application by name with intelligent mapping and window mode support."""
    try:
        if not name:
            return {"ok": False, "error": "No application name provided."}

        key = name.lower().strip()

        # detect window mode
        mode = "normal"
        if "minimized" in key:
            mode = "minimized"
            key = key.replace("minimized", "").strip()
        elif "maximized" in key:
            mode = "maximized"
            key = key.replace("maximized", "").strip()

        # unify synonyms
        synonyms = {
            "calculator": "calc",
            "calc": "calc",
            "notes": "notepad",
            "note pad": "notepad",
            "spotify": "spotify",
            "chrome": "chrome",
            "browser": "chrome",
            "edge": "msedge",
            "firefox": "firefox",
            "genshin": "genshin impact",
            "clash": "clash of clans",
            "coc": "clash of clans",
            "youtube": "https://www.youtube.com",
            "yt": "https://www.youtube.com",
            "google": "https://www.google.com",
            "file explorer": "explorer",
        }
        key = synonyms.get(key, key)

        # resolve possible executable path candidates
        candidates = []

        if key in APP_SHORTCUTS and os.path.exists(APP_SHORTCUTS[key]):
            candidates.append(APP_SHORTCUTS[key])
        if key in SYSTEM_APPS and os.path.exists(SYSTEM_APPS[key]):
            candidates.append(SYSTEM_APPS[key])
        exe_candidate = which(key + ".exe")
        if exe_candidate:
            candidates.append(exe_candidate)

        if candidates:
            exe_path = candidates[0]
            return open_with_exe(exe_path, mode=state)   # ✅ FIXED (used exe_path)

        # handle URLs
        if key.startswith("http"):
            return open_browser(key)
        if any(word in key for word in ["google", "youtube", "web", "search"]):
            return open_browser(f"https://www.google.com/search?q={shlex.quote(name)}")

        return {"ok": False, "error": f"Application '{name}' not found."}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def minimize_application(name):
    """Minimize a running window by app name."""
    try:
        if not name:
            return {"ok": False, "error": "No application name provided."}
        key = name.lower()
        for w in gw.getAllWindows():
            if key in w.title.lower():
                w.minimize()
                return {"ok": True, "out": f"Minimized {w.title}"}
        return {"ok": False, "error": f"No window found for '{name}'"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def restore_application(name):
    """Restore a minimized window by app name."""
    try:
        if not name:
            return {"ok": False, "error": "No application name provided."}
        key = name.lower()
        for w in gw.getAllWindows():
            if key in w.title.lower():
                w.restore()
                w.activate()
                return {"ok": True, "out": f"Restored {w.title}"}
        return {"ok": False, "error": f"No window found for '{name}'"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

def close_application(name):
    """Close an open application window by title match."""
    try:
        if not name:
            return {"ok": False, "error": "No application name provided."}
        key = name.lower()
        for w in gw.getAllWindows():
            if key in w.title.lower():
                w.close()
                return {"ok": True, "out": f"Closed {w.title}"}
        return {"ok": False, "error": f"No window found for '{name}'"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
