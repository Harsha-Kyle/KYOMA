import time
from typing import Dict, Any
from .LAV_logger import logger

class StartupSubsystem:
    def __init__(self, key: str, name: str, required: bool = True):
        self.key = key
        self.name = name
        self.required = required
        self.status = "pending"  # pending | initializing | ready | degraded | failed | skipped
        self.start_time: float = 0.0
        self.elapsed_s: float = 0.0
        self.detail: str = "Pending initialization"
        self.error: str | None = None
        self._parent: 'StartupProgress | None' = None  # set by StartupProgress

    def start(self, detail: str = ""):
        self.status = "initializing"
        self.start_time = time.time()
        if detail:
            self.detail = detail
        logger.info(f"[Startup] [{self.name}] Initializing... {detail}")

    def complete(self, detail: str = ""):
        self.status = "ready"
        if self.start_time > 0:
            self.elapsed_s = time.time() - self.start_time
        if detail:
            self.detail = detail
        logger.info(f"[Startup] [{self.name}] Ready in {self.elapsed_s:.2f}s ({self.detail})")
        # Notify parent to re-evaluate overall readiness
        if self._parent:
            self._parent._check_readiness()

    def skip(self, reason: str = "Optional service skipped"):
        self.status = "skipped"
        self.detail = reason
        logger.info(f"[Startup] [{self.name}] Skipped: {reason}")
        if self._parent:
            self._parent._check_readiness()

    def fail(self, error: str):
        self.status = "failed"
        self.error = error
        self.detail = f"Failed: {error}"
        if self.start_time > 0:
            self.elapsed_s = time.time() - self.start_time
        logger.error(f"[Startup] [{self.name}] FAILED in {self.elapsed_s:.2f}s: {error}")

    def degrade(self, warning: str):
        self.status = "degraded"
        self.detail = warning
        if self.start_time > 0:
            self.elapsed_s = time.time() - self.start_time
        logger.warning(f"[Startup] [{self.name}] Degraded: {warning}")
        # Degraded counts as "ready enough" — re-evaluate
        if self._parent:
            self._parent._check_readiness()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "required": self.required,
            "status": self.status,
            "elapsed_s": round(self.elapsed_s, 2),
            "detail": self.detail,
            "error": self.error,
        }

class StartupProgress:
    def __init__(self):
        self.boot_start_time = time.time()
        self.subsystems: Dict[str, StartupSubsystem] = {
            "imports": StartupSubsystem("imports", "Python Modules", required=True),
            "settings": StartupSubsystem("settings", "Settings Persistence", required=True),
            "ai_services": StartupSubsystem("ai_services", "Core AI Pipeline", required=True),
            "stt": StartupSubsystem("stt", "Microphone & STT", required=True),
            "tts": StartupSubsystem("tts", "Kokoro TTS Engine", required=True),
            "ollama": StartupSubsystem("ollama", "Ollama Connection", required=True),
            "model": StartupSubsystem("model", "Gemma Automation Model", required=True),
            "rvc": StartupSubsystem("rvc", "RVC Voice Cloning", required=False),
        }
        # Wire parent references so subsystem state changes trigger readiness re-eval
        for sub in self.subsystems.values():
            sub._parent = self
        self.current_step = 0
        self.total_steps = len(self.subsystems)
        self.current_message = "Initializing KYOMA System..."
        self.is_ready = False

    def show_step(self, text: str):
        self.current_step += 1
        self.current_message = text
        logger.info(f"[{self.current_step}/{self.total_steps}] {text}...")

    def complete_step(self, success_message: str | None = None):
        msg = success_message or f"{self.current_message} Complete"
        logger.info(f"[{self.current_step}/{self.total_steps}] {msg}")
        self._check_readiness()

    def get_subsystem(self, key: str) -> StartupSubsystem:
        if key not in self.subsystems:
            sub = StartupSubsystem(key, key.replace("_", " ").title())
            sub._parent = self
            self.subsystems[key] = sub
        return self.subsystems[key]

    def _check_readiness(self) -> bool:
        required_ok = True
        for sub in self.subsystems.values():
            if sub.required and sub.status not in ("ready", "degraded"):
                required_ok = False
                break
        self.is_ready = required_ok
        return self.is_ready

    def calculate_progress(self) -> int:
        """
        Calculate progress weighted by measured/estimated stage durations:
          imports:     60.53s  (51.5%)
          ai_services: 22.91s  (19.5%)
          settings:     4.06s  ( 3.5%)
          stt:          3.00s  ( 2.5%)
          tts:          3.97s  ( 3.4%)
          ollama:       1.50s  ( 1.3%)
          model:       26.12s  (22.2%)  — Gemma warmup
          rvc:          0.00s  ( 0.0%)  — optional, excluded from weight
        Actual completion status of each subsystem drives progress, not elapsed time.
        """
        WEIGHTS = {
            "imports":     60.53,
            "ai_services": 22.91,
            "settings":     4.06,
            "stt":          3.00,
            "tts":          3.97,
            "ollama":       1.50,
            "model":       26.12,
            "rvc":          0.00,  # optional, zero weight
        }
        total_weight = sum(WEIGHTS.get(k, 1.0) for k in self.subsystems if WEIGHTS.get(k, 1.0) > 0)
        if total_weight == 0:
            return 0
        completed_weight = 0.0
        for key, sub in self.subsystems.items():
            w = WEIGHTS.get(key, 1.0)
            if w == 0:
                continue
            if sub.status in ("ready", "skipped", "degraded"):
                completed_weight += w
            elif sub.status == "initializing" and sub.start_time > 0:
                # Partial credit: estimate progress within this stage based on elapsed vs expected
                elapsed = time.time() - sub.start_time
                expected = max(w, 1.0)
                partial = min(elapsed / expected, 0.95)  # cap at 95% until actually complete
                completed_weight += w * partial
        return int((completed_weight / total_weight) * 100)

    def get_status(self) -> Dict[str, Any]:
        self._check_readiness()
        total_elapsed = time.time() - self.boot_start_time
        pct = self.calculate_progress()
        active_sub = next((s for s in self.subsystems.values() if s.status == "initializing"), None)
        active_name = active_sub.name if active_sub else ("All systems ready" if self.is_ready else self.current_message)

        # Only claim 100% when ALL required subsystems (including Gemma model) are truly ready
        display_pct = 100 if self.is_ready else min(99, pct)

        return {
            "ready": self.is_ready,
            "percentage": display_pct,
            "step": self.current_step,
            "total_steps": self.total_steps,
            "message": active_name,
            "current_message": self.current_message,
            "elapsed_s": round(total_elapsed, 2),
            "subsystems": {k: v.to_dict() for k, v in self.subsystems.items()},
        }

startup_progress = StartupProgress()
