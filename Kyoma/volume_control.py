# volume_control.py

from pycaw.pycaw import AudioUtilities


def get_volume_interface():
    device = AudioUtilities.GetSpeakers()
    volume = device.EndpointVolume
    return volume


def set_volume(level):
    """Set the system volume to a specific level (0-100). Accepts int or string like '80%'."""
    if isinstance(level, str):
        level = level.strip().rstrip('%')
    try:
        level = int(float(level))
    except (ValueError, TypeError):
        level = 50
    level = max(0, min(level, 100))

    volume = get_volume_interface()
    volume.SetMasterVolumeLevelScalar(level / 100.0, None)

    return f"Volume set to {level}%"


def change_volume(direction: str):
    """Change the volume up or down. Direction should be 'up' or 'down'."""
    volume = get_volume_interface()

    current = volume.GetMasterVolumeLevelScalar()

    if direction == "up":
        new = min(1.0, current + 0.05)
    else:
        new = max(0.0, current - 0.05)

    volume.SetMasterVolumeLevelScalar(new, None)

    return f"Volume now {int(new*100)}%"


def mute_volume():
    """Mute the system volume."""
    volume = get_volume_interface()
    volume.SetMute(1, None)
    return "Volume muted"


def unmute_volume():
    """Unmute the system volume."""
    volume = get_volume_interface()
    volume.SetMute(0, None)
    return "Volume unmuted"


def get_volume():
    """Get the current system volume level (0-100)."""
    volume = get_volume_interface()
    level = int(volume.GetMasterVolumeLevelScalar() * 100)
    return level