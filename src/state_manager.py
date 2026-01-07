import json
import os
from pathlib import Path
from typing import Dict, Any
from .config import STATE_FILE

class StateManager:
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self.state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_file.exists():
            return {"processed_files": {}}
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: Corrupt state file {self.state_file}. Starting fresh.")
            return {"processed_files": {}}

    def save_state(self):
        # Atomic write for state file
        temp_file = self.state_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, self.state_file)

    def mark_processed(self, file_name: str, status: str, classification: Dict[str, Any] = None):
        """
        Updates the state for a given file.
        :param file_name: Name of the file (key).
        :param status: 'classified', 'completed', 'failed'.
        :param classification: result from classification step.
        """
        self.state["processed_files"][file_name] = {
            "status": status,
            "classification": classification,
            "timestamp": os.path.getmtime(self.state_file) if self.state_file.exists() else 0 # simplified
        }
        self.save_state()

    def is_processed(self, file_name: str) -> bool:
        return file_name in self.state["processed_files"] and \
               self.state["processed_files"][file_name]["status"] == "completed"

    def get_file_state(self, file_name: str) -> Dict[str, Any]:
        return self.state["processed_files"].get(file_name, {})
