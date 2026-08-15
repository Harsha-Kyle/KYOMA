# media_control.py
import ctypes
import time

# Windows virtual key codes for media keys
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

# Send key event
def press_key(hexKeyCode):
    ctypes.windll.user32.keybd_event(hexKeyCode, 0, 0, 0)
    ctypes.windll.user32.keybd_event(hexKeyCode, 0, 2, 0)  # keyup
    time.sleep(0.05)

# --- Controls ---
def play_pause():
    """Toggle play or pause for the current media."""
    press_key(VK_MEDIA_PLAY_PAUSE)
    return "Toggled Play/Pause "

def play():
    """Play the current media."""
    press_key(VK_MEDIA_PLAY_PAUSE)
    return "Toggled Play/Pause "

def next_track():
    """Skip to the next media track."""
    press_key(VK_MEDIA_NEXT_TRACK)
    return "Skipped to Next Track ⏭️"

def previous_track():
    """Go back to the previous media track."""
    press_key(VK_MEDIA_PREV_TRACK)
    press_key(VK_MEDIA_PREV_TRACK)
    return "Went to Previous Track ⏮️"

def startfrombegin_track():
    """Restart the current media track from the beginning."""
    press_key(VK_MEDIA_PREV_TRACK)
    return "Start from begining ⏮️"



