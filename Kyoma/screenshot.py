#screenshot.py
import os
import time
import threading
from datetime import datetime
from pathlib import Path
import pyautogui
import pygetwindow as gw
from PIL import Image
from winotify import Notification, audio
import win32clipboard

def clean_old_thumbs():
  """Delete all old thumbnail files at startup."""
  script_dir = Path(__file__).resolve().parent
  thumb_folder = script_dir / "Kyoma Screenshots" / "thumbs"
  if thumb_folder.exists():
    for f in thumb_folder.glob("*"):
      try:
        f.unlink()
      except Exception:
        pass
  else:
    thumb_folder.mkdir(parents=True, exist_ok=True)

def copy_image_to_clipboard(image_path):
  """Copy actual image data to clipboard (not just path)."""
  try:
    image = Image.open(image_path).convert("RGB")
    from io import BytesIO
    output_buffer = BytesIO()
    image.save(output_buffer, "BMP")
    data = output_buffer.getvalue()[14:]
    output_buffer.close()

    win32clipboard.OpenClipboard()
    win32clipboard.EmptyClipboard()
    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
    win32clipboard.CloseClipboard()
    return True
  except Exception as e:
    print("Clipboard error:", e)
    return False

def log_screenshot(file_path, app_name, copied):
  """Append a log entry to screenshot_log.txt."""
  try:
    script_dir = Path(__file__).resolve().parent
    log_file = script_dir / "Kyoma Screenshots" / "screenshot_log.txt"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Truncate path if it's too long
    full_path_str = str(file_path)
    if len(full_path_str) > 60:
        display_path = "..." + full_path_str[-60:]
    else:
        display_path = full_path_str

    with open(log_file, "a", encoding="utf-8") as log:
      log.write(
			f"[{datetime.now():%Y-%m-%d %H:%M:%S}] "
			f"File: {file_path.name:<35} | "
			f"App: {app_name:<15} | "
			f"Copied: {str(copied):<5} | "
			f"Path: {display_path}\n"
		)
  except Exception as e:
    print("Log write error:", e)

def take_screenshot_save(name=None, show=False):
  """Takes a screenshot, saves it, shows Windows-style notification with preview, copies to clipboard."""
  try:
    time.sleep(0.1)
    script_dir = Path(__file__).resolve().parent
    main_folder = script_dir / "Kyoma Screenshots"
    date_folder = main_folder / datetime.now().strftime("%Y-%m-%d")
    thumb_folder = main_folder / "thumbs"

    date_folder.mkdir(parents=True, exist_ok=True)
    thumb_folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%H-%M-%S")

    try:
      active_window = gw.getActiveWindow()
      app_name = active_window.title.split(" - ")[-1].split()[0] if active_window else "UnknownApp"
      if name:
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip()
        base_filename = f"{safe_name}_{timestamp}_{app_name}.png"
      else:
        base_filename = f"screenshot_{timestamp}_{app_name}.png"
    except Exception:
      app_name = "UnknownApp"
      base_filename = f"screenshot_{timestamp}.png"

    file_path = date_folder / base_filename
    counter = 1
    while file_path.exists():
      stem, suffix = file_path.stem, file_path.suffix
      file_path = date_folder / f"{stem}_{counter}{suffix}"
      counter += 1

    screenshot = pyautogui.screenshot()
    screenshot.save(file_path)

    if not file_path.exists() or file_path.stat().st_size == 0:
      raise RuntimeError("Screenshot file is empty.")

    # Save thumbnail in separate thumbs folder
    thumb_path = thumb_folder / f"thumb_{base_filename}"
    try:
      im = Image.open(file_path)
      im.thumbnail((300, 180))
      im.save(thumb_path)
    except Exception:
      thumb_path = None

    # Create Paint helper file
    edit_helper = script_dir / "open_in_paint.bat"
    with open(edit_helper, "w", encoding="utf-8") as f:
      f.write(f'start mspaint.exe "{file_path}"\nexit')

    copied = copy_image_to_clipboard(file_path)

    # Log the screenshot event
    log_screenshot(file_path, app_name, copied)

    # Windows notification
    try:
      msg_text = f"Saved to {date_folder}"
      toast = Notification(
        app_id="Kyoma Assistant",
        title="📸 Screenshot Taken",
        msg=msg_text,
        duration="short",
        icon=str(thumb_path if thumb_path and thumb_path.exists() else file_path)
      )
      toast.add_actions(label="View", launch=str(file_path))
      toast.add_actions(label="Edit", launch=str(edit_helper))
      toast.add_actions(label="Open Folder", launch=str(date_folder))
      toast.set_audio(audio.Default, loop=False)
      toast.show()
    except Exception as notif_err:
      print("Notification failed:", notif_err)

    # Cleanup helper file after use
    def cleanup_files():
      time.sleep(5)
      if edit_helper.exists():
        try:
          edit_helper.unlink()
        except Exception:
          pass

    threading.Thread(target=cleanup_files, daemon=True).start()

    if show:
      try:
        os.startfile(file_path)
      except Exception:
        pass

    return {"ok": True, "out": f"🖼️ Screenshot saved: {file_path}"}

  except Exception as e:
    return {"ok": False, "error": f"❌ Failed to take screenshot: {e}"}


# 🧹 Clean thumbnails on Kyoma startup
clean_old_thumbs()

