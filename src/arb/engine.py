from __future__ import annotations
import asyncio, time, math
from decimal import Decimal as D
from typing import Dict, Tuple, Callable, List
from core.types import BestBook, Opportunity, RuntimeConfig
from core.fees import Fees
from core.utils import now_s, net_bps as calc_net_bps

Confidence = float

class Detector:
    def __init__(self, fees: Fees, cfg: RuntimeConfig, publish_opp: Callable[[Opportunity], None]):
        self.fees = fees
        self.cfg = cfg
        self.publish_opp = publish_opp
        self.last_by_ex_pair: Dict[Tuple[str,str], BestBook] = {}

    def on_book(self, b: BestBook):
        self.last_by_ex_pair[(b.exchange, b.pair)] = b

    def _confidence(self, qty: D, bid_sz: D, ask_sz: D, age_s: float) -> Confidence:
        depth = float(min(bid_sz, ask_sz) / (qty if qty > 0 else D("1e-9")))
        depth_score = max(0.0, min(depth, 1.0))
        time_score = 1.0 if age_s <= 0.2 else max(0.0, 1.0 - (age_s - 0.2))
        return 0.5 * depth_score + 0.5 * time_score

    def scan_pair(self, pair: str):
        # gather fresh
        now = now_s()
        stale_s = self.cfg.stale_ms / 1000
        bids, asks = [], []
        for (ex, p), book in self.last_by_ex_pair.items():
            if p != pair: continue
            if (now - book.quote.ts) > stale_s: continue
            bids.append((ex, book.quote.bid, book.quote.bid_sz, book.quote.ts))
            asks.append((ex, book.quote.ask, book.quote.ask_sz, book.quote.ts))
        if not bids or not asks: return

        # try every ask x bid across exchanges
        for aex, aprice, asize, ats in asks:
            for bex, bprice, bsize, bts in bids:
                if aex == bex: continue
                nbps = calc_net_bps(bprice, aprice,
                                    self.fees.taker_bps(aex), self.fees.taker_bps(bex),
                                    int(self.cfg.slippage_bps_buffer))
                if nbps < self.cfg.min_profit_bps_after_fees:
                    continue

                # size: respect AUD cap
                aud_cap_qty = (D(self.cfg.max_trade_aud) / aprice).quantize(D("0.00000001"))
                qty = min(asize, bsize, aud_cap_qty)
                if qty <= 0: continue

                age_s = max(now - max(ats, bts), 0.0)
                conf = self._confidence(qty, bsize, asize, age_s)
                if conf < self.cfg.min_confidence: 
                    continue

                opp = Opportunity(
                    ts=now, pair=pair,
                    buy_ex=aex, sell_ex=bex,
                    buy_price=aprice, sell_price=bprice, qty=qty,
                    raw_bps=((bprice - aprice) / aprice) * D(10_000),
                    net_bps=nbps,
                    profit_aud=(bprice - aprice) * qty,
                    confidence=conf,
                    latency_ms=int(age_s * 1000)
                )
                self.publish_opp(opp)

    def full_scan(self, pairs: List[str]):
        for p in pairs:
            self.scan_pair(p)
