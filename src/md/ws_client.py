from __future__ import annotations
import asyncio, time
from decimal import Decimal as D
from typing import Callable, Dict, List
from core.types import BestBook, Quote
from core.utils import now_s
from core.symbol_map import unify_symbol

try:
    import ccxt.pro as ccxtpro
except Exception:
    ccxtpro = None

async def run_ws_exchange(ex_id: str, pairs: List[str], on_book: Callable[[BestBook], None]):
    if ccxtpro is None or not hasattr(ccxtpro, ex_id):
        raise RuntimeError(f"ccxt.pro WebSocket not available for '{ex_id}'")
    ex = getattr(ccxtpro, ex_id)({"enableRateLimit": True})
    try:
        await ex.load_markets()
        subscribe_pairs = [p for p in pairs if p in ex.markets]
        while True:
            for p in subscribe_pairs:
                ob = await ex.watch_order_book(p, limit=5)
                if not ob['bids'] or not ob['asks']:
                    continue
                bid_p, bid_sz = D(str(ob['bids'][0][0])), D(str(ob['bids'][0][1]))
                ask_p, ask_sz = D(str(ob['asks'][0][0])), D(str(ob['asks'][0][1]))
                qb = BestBook(
                    exchange=ex_id,
                    pair=unify_symbol(p),
                    quote=Quote(ts=now_s(), bid=bid_p, bid_sz=bid_sz, ask=ask_p, ask_sz=ask_sz)
                )
                on_book(qb)
    finally:
        await ex.close()
