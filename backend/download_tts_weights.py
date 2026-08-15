"""
Download GPT-SoVITS pretrained weights required for TTS to function.
Run this once from the backend directory with the venv active.
"""
import os
import sys

# Must be run from the backend directory
script_dir = os.path.dirname(os.path.abspath(__file__))
pretrained_dir = os.path.join(
    script_dir,
    "services", "TTS", "GPTsovits", "GPT_SoVITS", "pretrained_models"
)

print(f"Target directory: {pretrained_dir}")
os.makedirs(os.path.join(pretrained_dir, "gsv-v2final-pretrained"), exist_ok=True)
os.makedirs(os.path.join(pretrained_dir, "chinese-roberta-wwm-ext-large"), exist_ok=True)
os.makedirs(os.path.join(pretrained_dir, "chinese-hubert-base"), exist_ok=True)

try:
    from huggingface_hub import hf_hub_download, snapshot_download
except ImportError:
    print("huggingface_hub not found, installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "huggingface_hub"])
    from huggingface_hub import hf_hub_download, snapshot_download

# ── 1. GSV v2 main checkpoint ──────────────────────────────────────────────────
ckpt_path = os.path.join(
    pretrained_dir, "gsv-v2final-pretrained",
    "s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"
)
if not os.path.exists(ckpt_path):
    print("\n[1/4] Downloading s1bert (GPT) checkpoint (~1.8 GB)...")
    hf_hub_download(
        repo_id="lj1995/GPT-SoVITS",
        filename="gsv-v2final-pretrained/s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt",
        local_dir=pretrained_dir,
        local_dir_use_symlinks=False,
    )
    print("  ✓ Done.")
else:
    print("[1/4] s1bert checkpoint already exists, skipping.")

# ── 2. SoVITS weights ──────────────────────────────────────────────────────────
vits_path = os.path.join(pretrained_dir, "gsv-v2final-pretrained", "s2G2333k.pth")
if not os.path.exists(vits_path):
    print("\n[2/4] Downloading s2G (SoVITS) weights (~1.4 GB)...")
    hf_hub_download(
        repo_id="lj1995/GPT-SoVITS",
        filename="gsv-v2final-pretrained/s2G2333k.pth",
        local_dir=pretrained_dir,
        local_dir_use_symlinks=False,
    )
    print("  ✓ Done.")
else:
    print("[2/4] s2G weights already exist, skipping.")

# ── 3. Chinese-RoBERTa bert model ──────────────────────────────────────────────
bert_dir = os.path.join(pretrained_dir, "chinese-roberta-wwm-ext-large")
bert_model_bin = os.path.join(bert_dir, "pytorch_model.bin")
bert_model_safe = os.path.join(bert_dir, "model.safetensors")
if not (os.path.exists(bert_model_bin) or os.path.exists(bert_model_safe)):
    print("\n[3/4] Downloading chinese-roberta-wwm-ext-large (~1.3 GB)...")
    snapshot_download(
        repo_id="hfl/chinese-roberta-wwm-ext-large",
        local_dir=bert_dir,
        local_dir_use_symlinks=False,
        ignore_patterns=["*.msgpack", "*.h5", "flax_model*", "tf_model*", "rust_model*"],
    )
    print("  ✓ Done.")
else:
    print("[3/4] chinese-roberta-wwm-ext-large already exists, skipping.")

# ── 4. Chinese-HuBERT model ────────────────────────────────────────────────────
hubert_dir = os.path.join(pretrained_dir, "chinese-hubert-base")
hubert_model = os.path.join(hubert_dir, "pytorch_model.bin")
if not os.path.exists(hubert_model):
    print("\n[4/4] Downloading chinese-hubert-base (~360 MB)...")
    snapshot_download(
        repo_id="TencentGameMate/chinese-hubert-base",
        local_dir=hubert_dir,
        local_dir_use_symlinks=False,
    )
    print("  ✓ Done.")
else:
    print("[4/4] chinese-hubert-base already exists, skipping.")

print("\n✅ All pretrained weights downloaded successfully!")
print("Restart the backend server — TTS should now initialize correctly.")
