from __future__ import annotations
import yaml
from pathlib import Path
from typing import Dict

class Fees:
    def __init__(self, path: Path):
        d = yaml.safe_load(path.read_text())
        self.maker = d.get("maker_bps", {})
        self.taker = d.get("taker_bps", {})

    def taker_bps(self, ex: str) -> int:
        return int(self.taker.get(ex, 50))  # default safety
