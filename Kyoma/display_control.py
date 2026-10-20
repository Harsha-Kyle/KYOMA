# display_control.py
import ctypes
import screen_brightness_control as sbc
import subprocess
import platform
import wmi

def _clean_level(val, default):
    try:
        if isinstance(val, str):
            val = val.strip().rstrip('%')
        return int(float(val))
    except (ValueError, TypeError):
        return default

# ---------------------------
# BRIGHTNESS CONTROL
# ---------------------------
def set_brightness(level):
    """Set brightness to 0-100%"""
    try:
        level = _clean_level(level, 50)
        if level < 0 or level > 100:
            return f"Brightness must be 0-100%"
        sbc.set_brightness(level)
        return f"Brightness set to {level}%"
    except Exception as e:
        return f"Error setting brightness: {e}"

def get_brightness():
    """Get current brightness (average if multiple monitors)"""
    try:
        levels = sbc.get_brightness()
        if isinstance(levels, list):
            if not levels:
                return "Error: No monitors detected."
            avg = sum(levels)//len(levels)
            return f"Current brightness is {avg}%"
        return f"Current brightness is {levels}%"
    except Exception as e:
        return f"Error getting brightness: {e}"

def brightness_up(step=10):
    """Increase brightness by step% (default 10%)"""
    try:
        step = _clean_level(step, 10)
        current = sbc.get_brightness()
        if isinstance(current, list):
            if not current:
                return "Error: No monitors detected."
            current = sum(current)//len(current)
        new_level = min(current + step, 100)
        sbc.set_brightness(new_level)
        return f"Brightness increased to {new_level}%"
    except Exception as e:
        return f"Error increasing brightness: {e}"

def brightness_down(step=10):
    """Decrease brightness by step% (default 10%)"""
    try:
        step = _clean_level(step, 10)
        current = sbc.get_brightness()
        if isinstance(current, list):
            if not current:
                return "Error: No monitors detected."
            current = sum(current)//len(current)
        new_level = max(current - step, 0)
        sbc.set_brightness(new_level)
        return f"Brightness decreased to {new_level}%"
    except Exception as e:
        return f"Error decreasing brightness: {e}"



# ---------------------------
# MONITOR / SCREEN POWER
# ---------------------------
def lock_screen():
    """Lock the Windows session"""
    try:
        ctypes.windll.user32.LockWorkStation()
        return "Screen locked."
    except Exception as e:
        return f"Error locking screen: {e}"



