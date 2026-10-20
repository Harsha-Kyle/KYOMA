import secrets
from pathlib import Path

KEY_FILE = Path(__file__).parent / "data" / "api_key.txt"

def get_or_create_api_key() -> str:
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    key = secrets.token_urlsafe(32)
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    KEY_FILE.write_text(key)
    print(f"[KYOMA] Generated new API key: {key}")
    return key

API_KEY = get_or_create_api_key()
