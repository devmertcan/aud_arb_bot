from __future__ import annotations

# Basic map for common quirks. Extend as you see more.
XMAP = {
    "XBT/AUD": "BTC/AUD",
    "XDG/AUD": "DOGE/AUD",
    "XBT": "BTC",
    "XDG": "DOGE",
}

def unify_symbol(sym: str) -> str:
    return XMAP.get(sym, sym)
