import requests
import json
from typing import Generator, List, Dict
from .BaseLLM import BaseLLM
from services.lib.LAV_logger import logger

class OllamaLLM(BaseLLM):
    def __init__(self, model_name: str, base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

    def get_chat_completion(self, text: str, history: List[Dict[str, str]] = [], system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        url = f"{self.base_url}/api/chat"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
            
        for entry in history:
            messages.append(entry)
            
        messages.append({"role": "user", "content": text})
        
        # Map local sampling params to Ollama options
        options = {
            "temperature": kwargs.get("temperature", 0.8),
            "top_p": kwargs.get("top_p", 0.9),
            "top_k": kwargs.get("top_k", 40),
            "repeat_penalty": kwargs.get("repeat_penalty", 1.1),
            "seed": kwargs.get("seed", -1)
        }
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": options
        }
        
        try:
            response = requests.post(url, json=payload, stream=True)
            response.raise_for_status()
            
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if "message" in chunk and "content" in chunk["message"]:
                        yield chunk["message"]["content"]
                    if chunk.get("done"):
                        break
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield f"Error: Could not get response from Ollama ({e})"

    def complete_current_response(self, history: List[Dict[str, str]], system_prompt: str = "", **kwargs) -> Generator[str, None, None]:
        # Ollama's /api/chat handles the whole conversation, but if we want to "continue"
        # we just send the history. Ollama doesn't have a direct "continue from prompt" in /api/chat
        # like llama-cpp, so we just treat it as a normal chat completion with the history.
        return self.get_chat_completion("", history, system_prompt, **kwargs)
