"""
download_kokoro_weights.py — Download Kokoro ONNX model files (one-time setup).

Files saved to:
  backend/services/TTS/Kokoro/models/kokoro-v1.0.onnx  (~310 MB)
  backend/services/TTS/Kokoro/models/voices-v1.0.bin   (~  1 MB)

Run from the backend/ directory:
  python download_kokoro_weights.py
"""

import os
import sys
import urllib.request

BASE = os.path.join(os.path.dirname(__file__), "services", "TTS", "Kokoro", "models")
os.makedirs(BASE, exist_ok=True)

ASSETS = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin":  "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
}


def _reporthook(block, block_size, total):
    downloaded = block * block_size
    if total > 0:
        pct = min(100, downloaded * 100 // total)
        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
        mb_d = downloaded / 1_048_576
        mb_t = total / 1_048_576
        sys.stdout.write(f"\r  [{bar}] {pct:3d}%  {mb_d:.1f} / {mb_t:.1f} MB")
        sys.stdout.flush()
    else:
        sys.stdout.write(f"\r  Downloaded {downloaded / 1_048_576:.1f} MB…")
        sys.stdout.flush()


def main():
    for filename, url in ASSETS.items():
        dest = os.path.join(BASE, filename)
        if os.path.exists(dest):
            size_mb = os.path.getsize(dest) / 1_048_576
            print(f"✅ {filename} already exists ({size_mb:.1f} MB) — skipping.")
            continue

        print(f"\n⬇  Downloading {filename} …")
        try:
            urllib.request.urlretrieve(url, dest, reporthook=_reporthook)
            print(f"\n✅ Saved to {dest}")
        except Exception as e:
            print(f"\n❌ Failed: {e}")
            if os.path.exists(dest):
                os.remove(dest)
            sys.exit(1)

    print("\n🎉 All Kokoro model files are ready. Restart the backend server.")


if __name__ == "__main__":
    main()
