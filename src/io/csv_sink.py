from __future__ import annotations
import csv, os, time
from pathlib import Path
from core.types import BestBook, Opportunity

class CsvSink:
    def __init__(self, outdir: Path):
        self.outdir = outdir
        self.outdir.mkdir(parents=True, exist_ok=True)
        self._tob_path = self.outdir / "tob_snapshots.csv"
        self._opp_path = self.outdir / "opportunities.csv"
        self._ensure_headers()

    def _ensure_headers(self):
        if not self._tob_path.exists():
            with self._tob_path.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts_iso","ts","exchange","pair","bid","bid_sz","ask","ask_sz"])
        if not self._opp_path.exists():
            with self._opp_path.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["ts_iso","ts","pair","buy_ex","sell_ex","buy_price","sell_price",
                            "qty","raw_bps","net_bps","profit_aud","confidence","latency_ms"])

    def write_tob(self, b: BestBook):
        with self._tob_path.open("a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(b.quote.ts)),
                f"{b.quote.ts:.6f}", b.exchange, b.pair,
                str(b.quote.bid), str(b.quote.bid_sz), str(b.quote.ask), str(b.quote.ask_sz)
            ])

    def write_opp(self, o: Opportunity):
        with self._opp_path.open("a", newline="") as f:
            w = csv.writer(f)
            w.writerow([
                time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(o.ts)),
                f"{o.ts:.6f}", o.pair, o.buy_ex, o.sell_ex,
                str(o.buy_price), str(o.sell_price), str(o.qty),
                str(o.raw_bps), str(o.net_bps), str(o.profit_aud),
                f"{o.confidence:.3f}", o.latency_ms
            ])
