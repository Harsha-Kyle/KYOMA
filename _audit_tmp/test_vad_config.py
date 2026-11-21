import sys, os, json
sys.path.insert(0, 'backend')

# Simulate _load_vad_config logic inline (no import side effects)
defaults = {'vad_silence_duration': 0.45, 'vad_speech_threshold': 0.3}
cfg_path = os.path.abspath('Kyoma/kyoma_config.json')
with open(cfg_path, 'r', encoding='utf-8') as f:
    user_cfg = json.load(f)
for key in defaults:
    if key in user_cfg:
        defaults[key] = float(user_cfg[key])

sil_s = defaults["vad_silence_duration"]
sil_samples = int(sil_s * 16000)
thr = defaults["vad_speech_threshold"]
keys = list(user_cfg.keys())
print("VAD config loaded:")
print("  vad_silence_duration =", sil_s, "s (", sil_samples, "samples)")
print("  vad_speech_threshold =", thr)
print("  kyoma_config.json keys:", keys)
assert sil_s == 0.45, "Expected 0.45s silence duration"
assert thr == 0.3, "Expected 0.3 speech threshold"
assert sil_samples == 7200, "Expected 7200 samples for 0.45s @ 16kHz"
print("ALL ASSERTIONS PASSED")
