import win32gui
import win32con
import win32api
import pygetwindow as gw

def get_monitors():
    """Returns a list of monitor coordinates [(left, top, right, bottom), ...]."""
    return [m[2] for m in win32api.EnumDisplayMonitors()]

def tile_windows():
    """
    Tiles all visible, non-minimized windows side-by-side on the primary monitor.
    Use this to organize the workspace quickly.
    """
    windows = [w for w in gw.getAllWindows() if w.visible and not w.isMinimized and w.title != ""]
    # Filter out system windows
    blacklist = ["Program Manager", "Settings", "Microsoft Text Input Application", "Taskbar", "Task Manager"]
    windows = [w for w in windows if w.title not in blacklist]
    
    if not windows:
        return "No windows found to tile."
    
    # Sort windows by title to keep order consistent
    windows.sort(key=lambda x: x.title.lower())
    
    monitors = get_monitors()
    primary = monitors[0]
    m_width = primary[2] - primary[0]
    m_height = primary[3] - primary[1]
    
    width_per_window = m_width // len(windows)
    
    for i, w in enumerate(windows):
        try:
            w.restore() # Ensure it's not maximized/minimized
            w.moveTo(i * width_per_window, 0)
            w.resizeTo(width_per_window, m_height)
        except Exception as e:
            print(f"Error tiling window {w.title}: {e}")
        
    return f"Tiled {len(windows)} windows on the primary monitor."

def focus_only_active():
    """
    Closes all visible windows except for the one currently in focus. 
    Useful for 'Focus Mode' or cleaning up the desktop.
    """
    active_window = gw.getActiveWindow()
    if not active_window:
        return "Could not determine the active window."
    
    all_windows = [w for w in gw.getAllWindows() if w.visible and w.title != ""]
    blacklist = ["Program Manager", "Taskbar", "Settings", "Kyoma Assistant"]
    
    closed_count = 0
    for w in all_windows:
        # Don't close the active window, the taskbar, or Kyoma itself
        if w._hWnd != active_window._hWnd and w.title not in blacklist:
            try:
                w.close()
                closed_count += 1
            except Exception:
                pass
            
    return f"Focus Mode active. Closed {closed_count} background windows."

def move_to_monitor(app_name: str, monitor_index: int = 1):
    """
    Moves a specific application window to a different monitor.
    monitor_index: 0 for Primary, 1 for Secondary, etc.
    app_name: The name of the application (e.g., 'chrome', 'spotify').
    """
    monitors = get_monitors()
    if monitor_index >= len(monitors):
        return f"Monitor {monitor_index} not found. You have {len(monitors)} monitor(s) connected."
    
    target_monitor = monitors[monitor_index]
    
    # Find the window
    target_window = None
    for w in gw.getAllWindows():
        if app_name.lower() in w.title.lower() and w.visible:
            target_window = w
            break
            
    if not target_window:
        return f"Could not find an open window for '{app_name}'"
    
    try:
        target_window.restore()
        target_window.moveTo(target_monitor[0], target_monitor[1])
        # Optional: maximize after moving
        # target_window.maximize()
        return f"Successfully moved '{target_window.title}' to monitor {monitor_index}."
    except Exception as e:
        return f"Error moving window: {e}"
