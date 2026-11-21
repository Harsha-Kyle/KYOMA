import sys, os, time, json
sys.path.insert(0, os.path.abspath('Kyoma'))
sys.path.insert(0, os.path.abspath('backend'))
sys.stdout.reconfigure(encoding='utf-8')

import torch
import psutil

# 1. Device check
has_cuda = torch.cuda.is_available()
print(f"CUDA available: {has_cuda}")
if has_cuda:
    print(f"Device name: {torch.cuda.get_device_name(0)}")

# 2. Whisper baseline vs CPU
from faster_whisper import WhisperModel

def measure_whisper(device, compute_type):
    print(f"\n--- Testing Whisper on {device} ({compute_type}) ---")
    proc = psutil.Process()
    ram_before = proc.memory_info().rss / (1024*1024)
    vram_before = torch.cuda.memory_allocated() / (1024*1024) if has_cuda else 0
    
    t0 = time.perf_counter()
    model = WhisperModel("base", device=device, compute_type=compute_type)
    load_time = time.perf_counter() - t0
    
    ram_after = proc.memory_info().rss / (1024*1024)
    vram_after = torch.cuda.memory_allocated() / (1024*1024) if has_cuda else 0
    
    # Warmup / dummy transcription with synthetic wav
    dummy_wav = "backend/services/Input/voice_recording.wav"
    trans_time = 0
    if os.path.exists(dummy_wav):
        t1 = time.perf_counter()
        segments, _ = model.transcribe(dummy_wav, language="en")
        _ = list(segments)
        trans_time = time.perf_counter() - t1
    
    print(f"Load time: {load_time:.2f}s | Transcribe time: {trans_time:.3f}s")
    print(f"RAM diff: {ram_after - ram_before:.1f} MB | Total RAM: {ram_after:.1f} MB")
    if has_cuda:
        print(f"VRAM diff: {vram_after - vram_before:.1f} MB | Allocated VRAM: {vram_after:.1f} MB")
    return {
        "device": device,
        "compute_type": compute_type,
        "load_time": load_time,
        "trans_time": trans_time,
        "ram_mb": ram_after,
        "vram_mb": vram_after
    }

res_cuda = measure_whisper("cuda", "float16") if has_cuda else None
res_cpu = measure_whisper("cpu", "int8")

with open("_audit_tmp/whisper_experiment.json", "w") as f:
    json.dump({"cuda": res_cuda, "cpu": res_cpu}, f, indent=2)
print("\nWhisper experiment completed successfully.")
