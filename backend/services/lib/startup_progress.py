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

    def skip(self, reason: str = "Optional service skipped"):
        self.status = "skipped"
        self.detail = reason
        logger.info(f"[Startup] [{self.name}] Skipped: {reason}")

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
            self.subsystems[key] = StartupSubsystem(key, key.replace("_", " ").title())
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
        if not self.subsystems:
            return 0
        completed = sum(1 for s in self.subsystems.values() if s.status in ("ready", "skipped", "degraded"))
        total = len(self.subsystems)
        return int((completed / total) * 100)

    def get_status(self) -> Dict[str, Any]:
        self._check_readiness()
        total_elapsed = time.time() - self.boot_start_time
        pct = self.calculate_progress()
        active_sub = next((s for s in self.subsystems.values() if s.status == "initializing"), None)
        active_name = active_sub.name if active_sub else ("All systems ready" if self.is_ready else self.current_message)

        return {
            "ready": self.is_ready,
            "percentage": 100 if self.is_ready else min(95, pct),
            "step": self.current_step,
            "total_steps": self.total_steps,
            "message": active_name,
            "current_message": self.current_message,
            "elapsed_s": round(total_elapsed, 2),
            "subsystems": {k: v.to_dict() for k, v in self.subsystems.items()},
        }

startup_progress = StartupProgress()
