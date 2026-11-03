import sys
import os
import asyncio
import threading
from typing import Generator, List, Dict, Optional, Callable
from .BaseLLM import BaseLLM
from services.lib.LAV_logger import logger

# Add Kyoma directory to sys.path
kyoma_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "Kyoma"))
if kyoma_dir not in sys.path:
    sys.path.append(kyoma_dir)

# ── External hook ─────────────────────────────────────────────────────────────
# Set by server.py after init so KyomaLLM can broadcast state during a search
# without taking a hard dependency on the server module.
# Signature: async def broadcast_thinking(state: str) -> None
_broadcast_thinking_hook: Optional[Callable] = None
_event_loop_ref: Optional[asyncio.AbstractEventLoop] = None

def set_search_broadcast_hook(loop: asyncio.AbstractEventLoop, coro_factory: Callable):
    """
    Called once from server.py after startup.
    coro_factory(state: str) -> Coroutine that broadcasts state to WebUI + ESP32.
    """
    global _broadcast_thinking_hook, _event_loop_ref
    _broadcast_thinking_hook = coro_factory
    _event_loop_ref = loop


def _fire_state_broadcast(state: str):
    """
    Thread-safe: schedule a state broadcast on the server's event loop.
    Called from the synchronous executor thread during search.
    """
    if _broadcast_thinking_hook and _event_loop_ref:
        try:
            asyncio.run_coroutine_threadsafe(_broadcast_thinking_hook(state), _event_loop_ref)
        except Exception as _be:
            logger.debug(f"[KyomaLLM] State broadcast failed (non-fatal): {_be}")


class KyomaLLM(BaseLLM):
    def __init__(self, model_name: str = "Kyoma"):
        self.model_name = model_name
        self.kyoma_module = None
        self._loading = False
        self._load_error = None

        # Lazy-load in background thread so server startup is NOT blocked
        thread = threading.Thread(target=self._load_kyoma, daemon=True)
        thread.start()

    def _load_kyoma(self):
        self._loading = True
        try:
            import Kyoma_automation
            self.kyoma_module = Kyoma_automation
            logger.info("Kyoma automation module loaded successfully (background).")
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"Failed to import Kyoma_automation: {e}")
        finally:
            self._loading = False

    def _ensure_loaded(self):
        """Block until Kyoma module is loaded (only called at chat time, not startup)."""
        if self.kyoma_module:
            return True
        # If still loading, wait for it
        if self._loading:
            logger.info("Waiting for Kyoma module to finish loading...")
            import time
            for _ in range(60):  # wait up to 60s
                time.sleep(1)
                if not self._loading:
                    break
        if self.kyoma_module:
            return True
        # If not loaded yet and not loading, try once more synchronously
        if not self._load_error:
            try:
                import Kyoma_automation
                self.kyoma_module = Kyoma_automation
                return True
            except Exception as e:
                self._load_error = str(e)
        return False

    def get_chat_completion(self, text: str, history: List[Dict[str, str]] = [], system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        if not self._ensure_loaded():
            yield f"Error: Kyoma automation module could not be loaded: {self._load_error}"
            return

        # ── Fast path: direct command execution without LLM ─────────────────
        # Matches simple, unambiguous commands (volume, brightness, media, apps,
        # system info, etc.) and executes them instantly — saving ~1.5-5s per call.
        try:
            from fast_router import route as _fast_route
            fast_text, fast_handled = _fast_route(text)
            if fast_handled and fast_text:
                logger.info(f"[FastRouter] ⚡ Direct: {text!r} → {fast_text!r}")
                yield fast_text
                return
        except Exception as _fr_err:
            logger.warning(f"[FastRouter] Error (falling through to LLM): {_fr_err}")

        # ── Search fast-path: detect search intent, give immediate feedback ──
        # Check before full Ollama workflow to skip the first LLM tool-selection call.
        try:
            from ollama_workflow import is_search_query
            if is_search_query(text):
                logger.info(f"[KyomaLLM] Search intent detected: {text!r}")
                # Immediately yield spoken feedback (goes to TTS right away)
                yield "Let me look that up."
                # Broadcast thinking state to WebUI + ESP32 (non-blocking, best-effort)
                _fire_state_broadcast("thinking")
                # Fall through to full workflow which will now use the direct search path
        except Exception as _si_err:
            logger.debug(f"[KyomaLLM] Search intent check error (ignored): {_si_err}")

        # ── Slow path: full Ollama LLM + tool-call pipeline ─────────────────
        try:
            logger.info(f"Sending query to Kyoma automation: {text}")
            result = self.kyoma_module.query_ollama_with_tools(text)
            if result.get("ok"):
                yield result.get("text", "")
            else:
                yield f"Error from Kyoma: {result.get('error', 'Unknown error')}"
        except Exception as e:
            logger.error(f"Error in KyomaLLM execution: {e}")
            yield f"Error executing Kyoma automation: {e}"


    def complete_current_response(self, history: List[Dict[str, str]], system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        last_msg = ""
        if history:
            last_msg = history[-1].get("content", "")
        return self.get_chat_completion(last_msg, history, system_prompt, **kwargs)
