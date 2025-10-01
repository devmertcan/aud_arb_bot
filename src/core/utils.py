from __future__ import annotations
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Tuple
import orjson, time

D = Decimal

def now_s() -> float:
    return time.time()

def to_json(obj) -> bytes:
    return orjson.dumps(obj, option=orjson.OPT_SERIALIZE_NUMPY)

def quant(x: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return x
    q = (x / step).to_integral_value(rounding=ROUND_DOWN)
    return q * step

def bps(x: Decimal) -> Decimal:
    return x * D(10_000)

def net_bps(bid_p: D, ask_p: D, taker_buy_bps: int, taker_sell_bps: int, slip_bps: int) -> D:
    raw = (bid_p - ask_p) / ask_p
    return bps(raw) - D(taker_buy_bps) - D(taker_sell_bps) - D(slip_bps)
