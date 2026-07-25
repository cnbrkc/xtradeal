"""
Tarama durumunu (state) JSON dosyasında saklar.
Her çalışmada kaldığı yerden devam eder.
"""

import json
import os
from dataclasses import dataclass, asdict


@dataclass
class ScanState:
    last_page: int = 0
    last_post_id: str = ""
    total_pages: int = 0
    scan_count: int = 0


STATE_FILE = "data/scan_state.json"


class StateManager:

    def __init__(self, state_file: str = STATE_FILE):
        self.state_file = state_file
        os.makedirs(os.path.dirname(state_file), exist_ok=True)

    def load(self) -> ScanState:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return ScanState(**data)
            except (json.JSONDecodeError, TypeError):
                pass
        return ScanState()

    def save(self, state: ScanState):
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2, ensure_ascii=False)

    def update(self, last_page: int, last_post_id: str = "",
               total_pages: int = 0) -> ScanState:
        state = self.load()
        state.last_page = last_page
        if last_post_id:
            state.last_post_id = last_post_id
        if total_pages:
            state.total_pages = total_pages
        state.scan_count += 1
        self.save(state)
        return state
