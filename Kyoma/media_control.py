# media_control.py
import ctypes
import time
import subprocess
import re

# Windows virtual key codes for media keys (fallback)
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

def press_key(hexKeyCode):
    """Fallback keypress using Windows user32 keybd_event."""
    try:
        ctypes.windll.user32.keybd_event(hexKeyCode, 0, 0, 0)
        ctypes.windll.user32.keybd_event(hexKeyCode, 0, 2, 0)  # keyup
        time.sleep(0.05)
        return True
    except Exception:
        return False

def _run_media_ps(action: str) -> dict:
    """
    State-aware Windows Media Session control via Windows.Media.Control WinRT API.
    Returns dict: {'session': bool, 'status': str, 'action_taken': str}
    """
    ps_script = f"""
    try {{
        Add-Type -AssemblyName System.Runtime.WindowsRuntime
        $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
        [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media,ContentType=WindowsRuntime] | Out-Null
        $asyncOp = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()
        $task = $asTaskGeneric.MakeGenericMethod([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]).Invoke($null, @($asyncOp))
        $task.Wait(1200) | Out-Null
        $manager = $task.Result
        $session = $manager.GetCurrentSession()
        if (-not $session) {{
            Write-Output "NO_SESSION"
            exit
        }}
        $info = $session.GetPlaybackInfo()
        $status = $info.PlaybackStatus.ToString()
        $action = "{action}"

        if ($action -eq "status") {{
            Write-Output "STATUS:$status"
        }} elseif ($action -eq "play") {{
            if ($status -eq "Playing") {{
                Write-Output "ALREADY_PLAYING"
            }} else {{
                $op = $session.TryPlayAsync()
                $t = $asTaskGeneric.MakeGenericMethod([bool]).Invoke($null, @($op))
                $t.Wait(800) | Out-Null
                Write-Output "PLAY_SUCCESS"
            }}
        }} elseif ($action -eq "pause" -or $action -eq "stop") {{
            if ($status -eq "Paused" -or $status -eq "Stopped") {{
                Write-Output "ALREADY_PAUSED"
            }} else {{
                $op = $session.TryPauseAsync()
                $t = $asTaskGeneric.MakeGenericMethod([bool]).Invoke($null, @($op))
                $t.Wait(800) | Out-Null
                Write-Output "PAUSE_SUCCESS"
            }}
        }} elseif ($action -eq "next") {{
            $op = $session.TrySkipNextAsync()
            $t = $asTaskGeneric.MakeGenericMethod([bool]).Invoke($null, @($op))
            $t.Wait(800) | Out-Null
            Write-Output "NEXT_SUCCESS"
        }} elseif ($action -eq "prev") {{
            $op = $session.TrySkipPreviousAsync()
            $t = $asTaskGeneric.MakeGenericMethod([bool]).Invoke($null, @($op))
            $t.Wait(800) | Out-Null
            Write-Output "PREV_SUCCESS"
        }}
    }} catch {{
        Write-Output "ERR:$($_.Exception.Message)"
    }}
    """
    try:
        p = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_script],
            capture_output=True, text=True, timeout=2.0
        )
        out = p.stdout.strip()
        return {"raw": out}
    except Exception as e:
        return {"raw": f"ERR:{e}"}

# --- State-Aware Controls ---

def play_pause():
    """Toggle play or pause state."""
    res = _run_media_ps("status")
    raw = res.get("raw", "")
    if "STATUS:Playing" in raw:
        return pause()
    elif "STATUS:Paused" in raw:
        return play()
    # Fallback if no active session detected
    press_key(VK_MEDIA_PLAY_PAUSE)
    return "Done."

def play():
    """Idempotently resume media playback. Never toggles or pauses if already playing."""
    res = _run_media_ps("play")
    raw = res.get("raw", "")
    if "ALREADY_PLAYING" in raw:
        return "Already playing."
    if "PLAY_SUCCESS" in raw:
        return "Playing."
    # Fallback to media key
    press_key(VK_MEDIA_PLAY_PAUSE)
    return "Playing."

def pause():
    """Idempotently pause media playback. Never starts playback if already paused."""
    res = _run_media_ps("pause")
    raw = res.get("raw", "")
    if "ALREADY_PAUSED" in raw:
        return "Already paused."
    if "PAUSE_SUCCESS" in raw:
        return "Paused."
    # If no active session exposes controls, use key toggle only when user requested pause
    press_key(VK_MEDIA_PLAY_PAUSE)
    return "Paused."

def next_track():
    """Skip to the next media track."""
    res = _run_media_ps("next")
    if "NEXT_SUCCESS" not in res.get("raw", ""):
        press_key(VK_MEDIA_NEXT_TRACK)
    return "Next track."

def previous_track():
    """Go back to the previous media track."""
    res = _run_media_ps("prev")
    if "PREV_SUCCESS" not in res.get("raw", ""):
        press_key(VK_MEDIA_PREV_TRACK)
        press_key(VK_MEDIA_PREV_TRACK)
    return "Previous track."

def startfrombegin_track():
    """Restart the current media track from the beginning."""
    press_key(VK_MEDIA_PREV_TRACK)
    return "Playing from the beginning."
