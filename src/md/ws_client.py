from __future__ import annotations
import asyncio
from decimal import Decimal as D
from typing import Callable, List, Optional
from core.types import BestBook, Quote
from core.utils import now_s
from core.symbol_map import unify_symbol

try:
    import ccxt.pro as ccxtpro
except Exception:
    ccxtpro = None

async def run_ws_exchange(ex_id: str, pairs: List[str], on_book: Callable[[BestBook], None], ob_limit: Optional[int] = None):
    if ccxtpro is None or not hasattr(ccxtpro, ex_id):
        raise RuntimeError(f"ccxt.pro WebSocket not available for '{ex_id}'")
    ex = getattr(ccxtpro, ex_id)({"enableRateLimit": True})
    try:
        await ex.load_markets()
        subscribe_pairs = [p for p in pairs if p in ex.markets]

        # default safe limits per exchange if not provided by config
        default_limits = {"kraken": 10, "okx": 5}
        limit = ob_limit if ob_limit is not None else default_limits.get(ex_id, None)

        while True:
            for p in subscribe_pairs:
                try:
                    ob = await (ex.watch_order_book(p, limit=limit) if limit is not None
                                else ex.watch_order_book(p))
                except Exception as e:
                    # Kraken throws if limit not in {10,25,100,500,1000}; auto-correct to 10
                    msg = str(e).lower()
                    if ex_id == "kraken" and ("accepts limit values" in msg or "limit" in msg):
                        limit = 10
                        continue
                    raise

                if not ob.get('bids') or not ob.get('asks'):
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
