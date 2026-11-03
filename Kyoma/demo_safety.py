import os
import json
import re

def is_demo_mode_active():
    """Check if demo mode is enabled via config or environment."""
    if os.environ.get("KYOMA_DEMO_MODE", "").lower() in ("1", "true", "yes"):
        return True
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "kyoma_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                return bool(json.load(f).get("demo_mode", False))
    except Exception:
        pass
    return False

def check_demo_mode_refusal(action_name: str, args: dict = None) -> tuple[bool, str]:
    """
    Check if an action is disabled during demo mode.
    Disables: lock_screen, close_application, focus_only_active.
    Returns (is_refused, polite_spoken_refusal).
    """
    if not is_demo_mode_active():
        return False, ""
    
    act = (action_name or "").lower().strip()
    if act in ("lock_screen", "lock_pc", "lock"):
        return True, "Locking the screen is disabled during demo mode to ensure a smooth presentation."
    if act in ("close_application", "close_app", "close"):
        target = ""
        if args and isinstance(args, dict):
            target = args.get("name", "applications")
        target_str = f" {target}" if target else ""
        return True, f"Closing{target_str} is disabled during demo mode for presentation safety."
    if act in ("focus_only_active", "minimize_all_except"):
        return True, "Window isolation is disabled during demo mode for presentation safety."
        
    return False, ""
