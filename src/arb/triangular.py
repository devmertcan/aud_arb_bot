from __future__ import annotations
from decimal import Decimal as D
from typing import Dict, Tuple, List, Callable, Optional
from core.types import BestBook, TriOpportunity, RuntimeConfig
from core.fees import Fees
from core.utils import now_s

class TriDetector:
    """
    Single-exchange triangular arb scanner.
    Uses top-of-book for BASE/QUOTE pairs to build directed currency graph.
    Each pair contributes two edges:
      QUOTE -> BASE : buy BASE with QUOTE at ask (rate = (1-fee-slip)/ask, max_in = ask_sz*ask)
      BASE -> QUOTE : sell BASE for QUOTE at bid (rate = (1-fee-slip)*bid, max_in = bid_sz)
    """
    def __init__(self, fees: Fees, cfg: RuntimeConfig, publish_tri: Callable[[TriOpportunity], None]):
        self.fees = fees
        self.cfg = cfg
        self.publish_tri = publish_tri
        # latest quotes per (exchange, pair)
        self.last: Dict[Tuple[str,str], BestBook] = {}

    def on_book(self, b: BestBook):
        self.last[(b.exchange, b.pair)] = b

    def _edges_for_exchange(self, ex: str, stale_s: float):
        now = now_s()
        edges: Dict[Tuple[str,str], dict] = {}
        currencies = set()

        fee_bps = self.fees.taker_bps(ex)
        slip_bps = int(self.cfg.slippage_bps_buffer)
        fee_k = (D(10_000) - D(fee_bps) - D(slip_bps)) / D(10_000)

        for (e, pair), book in self.last.items():
            if e != ex: continue
            if (now - book.quote.ts) > stale_s: continue
            try:
                base, quote = pair.split("/")
            except ValueError:
                continue
            currencies.add(base); currencies.add(quote)

            bid, ask = D(book.quote.bid), D(book.quote.ask)
            bid_sz, ask_sz = D(book.quote.bid_sz), D(book.quote.ask_sz)
            age_s = now - book.quote.ts

            # QUOTE -> BASE (buy BASE with QUOTE)
            if ask > 0 and ask_sz > 0:
                rate_q2b = fee_k / ask                # output BASE per 1 QUOTE
                max_in_q = ask_sz * ask               # max input QUOTE to stay within top size
                edges[(quote, base)] = {"rate": rate_q2b, "max_in": max_in_q, "pair": pair,
                                        "side": "buy", "price": ask, "age_s": age_s}

            # BASE -> QUOTE (sell BASE for QUOTE)
            if bid > 0 and bid_sz > 0:
                rate_b2q = fee_k * bid                # output QUOTE per 1 BASE
                max_in_b = bid_sz                     # max input BASE
                edges[(base, quote)] = {"rate": rate_b2q, "max_in": max_in_b, "pair": pair,
                                        "side": "sell", "price": bid, "age_s": age_s}

        return edges, sorted(currencies)

    def _apply(self, amount_in: D, edge: dict) -> tuple[D, bool]:
        # Cap by available input capacity (edge['max_in'])
        usable = min(amount_in, D(edge["max_in"]))
        return (usable * D(edge["rate"])), (amount_in > edge["max_in"])

    def scan_exchange(self, ex: str, start_aud: Optional[D] = None):
        start = D(str(start_aud if start_aud is not None else self.cfg.tri_start_aud))
        stale_s = self.cfg.stale_ms / 1000.0
        edges, currencies = self._edges_for_exchange(ex, stale_s)
        if not currencies or "AUD" not in currencies:
            return

        now = now_s()
        # enumerate triangles: AUD -> X -> Y -> AUD
        for X in currencies:
            if X == "AUD": continue
            e1 = edges.get(("AUD", X))
            if not e1: continue
            for Y in currencies:
                if Y == "AUD" or Y == X: continue
                e2 = edges.get((X, Y))
                e3 = edges.get((Y, "AUD"))
                if not e2 or not e3: 
                    continue

                # All edges must be fresh enough (already filtered), but compute latency
                latency_ms = int(1000 * max(e1["age_s"], e2["age_s"], e3["age_s"]))

                # propagate amount with capacity constraints
                amount1, c1 = self._apply(start, e1)     # AUD -> X   (buy X with AUD)
                if amount1 <= 0: continue
                amount2, c2 = self._apply(amount1, e2)   # X -> Y
                if amount2 <= 0: continue
                amount3, c3 = self._apply(amount2, e3)   # Y -> AUD (final)

                end = amount3
                if end <= 0:
                    continue

                net_bps = ( (end - start) / start ) * D(10_000)
                if net_bps < self.cfg.min_profit_bps_after_fees:
                    continue

                # confidence: depth usage + timeliness
                def depth_score(ai, edge):
                    # if we used less than 50% of max_in, good (1.0); else degrade
                    ratio = float((ai / D(edge["max_in"])) if D(edge["max_in"]) > 0 else 0)
                    return 1.0 if ratio <= 0.5 else max(0.0, 1.0 - (ratio - 0.5) * 2.0)

                conf_depth = (depth_score(start, e1) + depth_score(amount1, e2) + depth_score(amount2, e3)) / 3.0
                conf_time = 1.0 if latency_ms <= 200 else max(0.0, 1.0 - (latency_ms - 200) / 800.0)
                confidence = 0.5 * conf_depth + 0.5 * conf_time

                if confidence < self.cfg.min_confidence:
                    continue

                tri = TriOpportunity(
                    ts=now, exchange=ex, path=["AUD", X, Y, "AUD"],
                    start_aud=start, end_aud=end,
                    net_bps=net_bps, profit_aud=(end - start),
                    confidence=confidence, latency_ms=latency_ms,
                    legs=[
                        {"pair": e1["pair"], "side": e1["side"], "price": str(e1["price"]),
                         "max_in": str(e1["max_in"]), "age_s": round(e1["age_s"], 3)},
                        {"pair": e2["pair"], "side": e2["side"], "price": str(e2["price"]),
                         "max_in": str(e2["max_in"]), "age_s": round(e2["age_s"], 3)},
                        {"pair": e3["pair"], "side": e3["side"], "price": str(e3["price"]),
                         "max_in": str(e3["max_in"]), "age_s": round(e3["age_s"], 3)},
                    ]
                )
                self.publish_tri(tri)
