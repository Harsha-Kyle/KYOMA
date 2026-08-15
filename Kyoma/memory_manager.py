class MemoryManager:
    def __init__(self, max_history=10):
        self.max_history = max_history
        self.history = []

    def add_user_message(self, text):
        self.history.append({"role": "user", "content": text})
        self._trim()

    def add_assistant_message(self, text=None, tool_calls=None):
        msg = {"role": "assistant"}
        if text:
            msg["content"] = text
        if tool_calls:
            msg["tool_calls"] = tool_calls
        self.history.append(msg)
        self._trim()

    def add_tool_message(self, text, name=None):
        self.history.append({"role": "tool", "content": text, "name": name})
        self._trim()

    def get_messages(self, system_prompt=None):
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        msgs.extend(self.history)
        return msgs

    def _trim(self):
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def clear(self):
        self.history = []
