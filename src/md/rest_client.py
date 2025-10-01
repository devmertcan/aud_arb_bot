from __future__ import annotations
import asyncio
from decimal import Decimal as D
from typing import Callable, List, Optional
import ccxt
from core.types import BestBook, Quote
from core.utils import now_s
from core.symbol_map import unify_symbol

async def run_rest_exchange(ex_id: str, pairs: List[str], poll_ms: int, on_book: Callable[[BestBook], None], ob_limit: Optional[int] = None):
    ex = getattr(ccxt, ex_id)({"enableRateLimit": True})
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, ex.load_markets)
    avail = [p for p in pairs if p in ex.markets]

    async def poll_pair(p: str):
        while True:
            try:
                if ob_limit is not None:
                    ob = await loop.run_in_executor(None, ex.fetch_order_book, p, ob_limit)
                else:
                    ob = await loop.run_in_executor(None, ex.fetch_order_book, p, 5)
                if ob.get('bids') and ob.get('asks'):
                    bid_p, bid_sz = D(str(ob['bids'][0][0])), D(str(ob['bids'][0][1]))
                    ask_p, ask_sz = D(str(ob['asks'][0][0])), D(str(ob['asks'][0][1]))
                else:
                    t = await loop.run_in_executor(None, ex.fetch_ticker, p)
                    bid_p, ask_p = D(str(t['bid'])), D(str(t['ask']))
                    bid_sz = ask_sz = D("0.1")
                qb = BestBook(
                    exchange=ex_id,
                    pair=unify_symbol(p),
                    quote=Quote(ts=now_s(), bid=bid_p, bid_sz=bid_sz, ask=ask_p, ask_sz=ask_sz)
                )
                on_book(qb)
            except Exception:
                pass
            await asyncio.sleep(poll_ms / 1000)

    await asyncio.gather(*(poll_pair(p) for p in avail))
