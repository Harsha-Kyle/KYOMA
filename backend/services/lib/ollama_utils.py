import os
import subprocess
import time
import requests
from services.lib.LAV_logger import logger

def ensure_ollama_running(base_url: str = "http://localhost:11434", timeout: int = 20) -> bool:
    """
    Checks if Ollama is running, and attempts to start it if not.
    Specifically targets Windows implementation.
    """
    check_url = f"{base_url}/api/tags"
    
    # 1. Check if already running
    try:
        response = requests.get(check_url, timeout=2)
        if response.status_code == 200:
            logger.debug("Ollama is already running.")
            return True
    except (requests.exceptions.RequestException, Exception):
        pass

    logger.info("Ollama is offline. Attempting to start it...")

    # 2. Find Ollama executable
    # Common Windows installation paths
    paths_to_try = [
        "ollama",  # Try if it's in PATH
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama\ollama.exe"),
        r"C:\Program Files\Ollama\ollama.exe",
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe")
    ]

    started = False
    for path in paths_to_try:
        try:
            # Check if file exists if it's an absolute path
            if os.path.isabs(path) and not os.path.exists(path):
                continue

            # Start Ollama service in background
            # CREATE_NO_WINDOW is 0x08000000 on Windows to prevent console popup
            creation_flags = 0x08000000 if os.name == 'nt' else 0
            
            subprocess.Popen(
                [path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creation_flags,
                shell=False
            )
            started = True
            logger.info(f"Started Ollama process via: {path}")
            break
        except Exception as e:
            logger.debug(f"Failed to start Ollama from {path}: {e}")
            continue

    if not started:
        logger.warning("Could not find or start Ollama executable.")
        return False

    # 3. Wait for service to become ready
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(check_url, timeout=1)
            if response.status_code == 200:
                logger.info("Ollama service is now ready.")
                return True
        except:
            pass
        time.sleep(2)
        logger.info(f"Waiting for Ollama... ({int(time.time() - start_time)}s)")

    logger.error("Ollama failed to start within the timeout period.")
    return False
