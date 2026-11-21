import json
import os
import re
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

class HistoryStore:
    def __init__(self, sessions_dir_name: str = "chat_sessions"):
        self.sessions_dir = os.path.join(os.path.dirname(__file__), sessions_dir_name)
        self.counter_file = os.path.join(os.path.dirname(__file__), "chat_counter.json")
        self._ensure_sessions_dir()

    def _ensure_sessions_dir(self) -> None:
        if not os.path.exists(self.sessions_dir):
            os.makedirs(self.sessions_dir)

    def _get_session_path(self, session_id: str) -> str:
        return os.path.join(self.sessions_dir, f"{session_id}.json")

    def _get_next_chat_number(self) -> int:
        """Get next sequential chat number using a persistent counter file."""
        next_num = None
        if os.path.exists(self.counter_file):
            try:
                with open(self.counter_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    next_num = int(data.get("next_number", 1))
            except Exception:
                next_num = None

        if next_num is None:
            # Determine starting number from existing session files
            max_num = 0
            if os.path.exists(self.sessions_dir):
                for fname in os.listdir(self.sessions_dir):
                    if fname.endswith(".json"):
                        try:
                            with open(os.path.join(self.sessions_dir, fname), "r", encoding="utf-8") as f:
                                sdata = json.load(f)
                                title = sdata.get("title", "")
                                m = re.search(r"Chat\s*#?\s*(\d+)", title, re.IGNORECASE)
                                if m:
                                    max_num = max(max_num, int(m.group(1)))
                        except Exception:
                            continue
            next_num = max_num + 1

        # Persist updated counter (incremented)
        try:
            with open(self.counter_file, 'w', encoding='utf-8') as f:
                json.dump({"next_number": next_num + 1}, f, indent=2)
        except Exception:
            pass

        return next_num

    def create_session(self, title: Optional[str] = None) -> Dict[str, Any]:
        """Create a new chat session with sequential numbering."""
        session_id = str(uuid.uuid4())
        
        is_default = (
            not title or 
            title.strip() in ("", "New Chat", "New Session", "New") or 
            bool(re.match(r"^Chat\s*#?\s*\d*$", title.strip(), re.IGNORECASE))
        )

        if is_default:
            num = self._get_next_chat_number()
            session_title = f"Chat {num}"
            manually_renamed = False
        else:
            session_title = title.strip()
            manually_renamed = True

        session_data = {
            "id": session_id,
            "title": session_title,
            "created_at": datetime.now().isoformat(),
            "history": [],
            "indexed": False,
            "indexed_at": None,
            "manually_renamed": manually_renamed
        }
        
        session_path = self._get_session_path(session_id)
        with open(session_path, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)
            
        return session_data

    def update_session(self, session_id: str, history: List[Dict[str, str]]) -> bool:
        session_path = self._get_session_path(session_id)
        if not os.path.exists(session_path):
            return False
            
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            session_data["history"] = history
            
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            return True
        except (json.JSONDecodeError, IOError):
            return False

    def update_session_title(self, session_id: str, title: str, manually_renamed: bool = True) -> bool:
        session_path = self._get_session_path(session_id)
        if not os.path.exists(session_path):
            return False
            
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            session_data["title"] = title
            session_data["manually_renamed"] = manually_renamed
            
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            return True
        except (json.JSONDecodeError, IOError):
            return False

    def generate_title_from_history(self, session_id: str) -> Optional[str]:
        """
        Generate a meaningful, concise, memorable title based on conversation content.
        Preserves manually renamed chats.
        Retries generic conversations later if substantive messages are added.
        """
        session_data = self.get_session_history(session_id)
        if not session_data:
            return None

        # Rule: Never overwrite manually renamed chats
        if session_data.get("manually_renamed", False):
            return None

        history = session_data.get("history", [])
        if not history:
            return None

        # Find first meaningful user prompt
        user_msgs = [m.get("content", "").strip() for m in history if m.get("role") == "user" and m.get("content", "").strip()]
        if not user_msgs:
            return None

        # Check if conversation is only generic greetings
        first_user = user_msgs[0]
        cleaned_first = re.sub(r"[^\w\s]", "", first_user).strip().lower()
        generic_greetings = {"hi", "hello", "hey", "yo", "test", "are you there", "ok", "okay", "bye", "good"}
        
        # If first message was just a greeting, check if later user messages have substance
        topic_msg = None
        if cleaned_first in generic_greetings or len(cleaned_first.split()) <= 1:
            for later_msg in user_msgs[1:]:
                c = re.sub(r"[^\w\s]", "", later_msg).strip().lower()
                if c not in generic_greetings and len(c.split()) > 1:
                    topic_msg = later_msg
                    break
            if not topic_msg:
                # Still generic greetings only — keep Chat N for now, do not assign a generic title
                return None
        else:
            topic_msg = first_user

        # Generate a concise title
        new_title = None
        try:
            import ollama
            prompt = (
                f"Generate a short, memorable 3 to 5 word title summarizing this question or topic: '{topic_msg}'. "
                "Output ONLY the title text. Do not use quotation marks, colons, or trailing punctuation."
            )
            res = ollama.chat(
                model="gemma4:e2b",
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 12}
            )
            generated = res.get("message", {}).get("content", "").strip()
            # Clean up quotes and symbols
            generated = re.sub(r'["\'\*\#\.\,\:\;]', '', generated).strip()
            words = generated.split()
            if 1 <= len(words) <= 7:
                new_title = " ".join(words[:6]).title()
        except Exception:
            pass

        # Robust heuristic fallback if Ollama is busy or unreachable
        if not new_title:
            # Clean topic_msg to form a high-quality title
            clean = re.sub(r'^(?:what\s+is|what\s+are|how\s+to|can\s+you|please|tell\s+me\s+about|explain)\s+', '', topic_msg, flags=re.IGNORECASE)
            clean = re.sub(r'["\'\*\#\.\,\:\;\?\!]', '', clean).strip()
            words = clean.split()
            if words:
                new_title = " ".join(words[:5]).title()

        if new_title and len(new_title) >= 3:
            self.update_session_title(session_id, new_title, manually_renamed=False)
            return new_title

        return None

    def mark_session_indexed(self, session_id: str, indexed: bool = True) -> bool:
        session_path = self._get_session_path(session_id)
        if not os.path.exists(session_path):
            return False
            
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            session_data["indexed"] = indexed
            session_data["indexed_at"] = datetime.now().isoformat() if indexed else None
            
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            return True
        except (json.JSONDecodeError, IOError):
            return False

    def get_session_list(self) -> List[Dict[str, Any]]:
        sessions = []
        for filename in os.listdir(self.sessions_dir):
            if filename.endswith('.json'):
                try:
                    with open(os.path.join(self.sessions_dir, filename), 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                        sessions.append({
                            "id": session_data["id"],
                            "title": session_data["title"],
                            "created_at": session_data["created_at"],
                            "indexed": session_data.get("indexed", False),
                            "indexed_at": session_data.get("indexed_at"),
                            "manually_renamed": session_data.get("manually_renamed", False),
                            "history": session_data.get("history", [])
                        })
                except (json.JSONDecodeError, IOError):
                    continue
        return sorted(sessions, key=lambda x: x["created_at"], reverse=True)

    def get_session_history(self, session_id: str) -> Optional[Dict[str, Any]]:
        session_path = self._get_session_path(session_id)
        if not os.path.exists(session_path):
            return None
            
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def delete_session(self, session_id: str) -> bool:
        session_path = self._get_session_path(session_id)
        if os.path.exists(session_path):
            try:
                os.remove(session_path)
                return True
            except IOError:
                return False
        return False
