import sys
import os
import threading
from typing import Generator, List, Dict
from .BaseLLM import BaseLLM
from services.lib.LAV_logger import logger

# Add Kyoma directory to sys.path
kyoma_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "Kyoma"))
if kyoma_dir not in sys.path:
    sys.path.append(kyoma_dir)

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
