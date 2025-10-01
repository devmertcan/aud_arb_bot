from __future__ import annotations
import asyncio, yaml, os
from pathlib import Path
from decimal import Decimal as D
from typing import List, Callable
from core.types import RuntimeConfig, BestBook, Opportunity
from core.fees import Fees
from core.utils import now_s
from md.aggregator import Aggregator
from md.ws_client import run_ws_exchange
from md.rest_client import run_rest_exchange
from io.csv_sink import CsvSink
from arb.engine import Detector
from io.dashboard_api import make_app
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
OUT = ROOT.parent / "out"

def load_yaml(p: Path): 
    return yaml.safe_load(p.read_text())

def load_runtime() -> RuntimeConfig:
    d = load_yaml(CONFIG / "runtime.yml")["runtime"]
    # coerce numerics to Decimal where needed
    d["max_trade_aud"] = D(str(d["max_trade_aud"]))
    d["min_profit_bps_after_fees"] = D(str(d["min_profit_bps_after_fees"]))
    d["slippage_bps_buffer"] = D(str(d["slippage_bps_buffer"]))
    return RuntimeConfig(**d)

async def run():
    pairs = load_yaml(CONFIG / "pairs.yml")["pairs"]
    exs = [e for e in load_yaml(CONFIG / "exchanges.yml")["exchanges"] if e.get("enabled")]
    fees = Fees(CONFIG / "fees.yml")
    cfg = load_runtime()

    agg = Aggregator()
    sink = CsvSink(OUT)
    # write all top-of-book snapshots to CSV (optional but handy)
    agg.subscribe(lambda b: sink.write_tob(b))

    # publish function used by detector
    latest: list[Opportunity] = []
    subs: list = []

    def publish_opp(opp: Opportunity):
        sink.write_opp(opp)
        latest.insert(0, opp)
        if len(latest) > 500:
            latest.pop()

    detector = Detector(fees, cfg, publish_opp)

    # feed detector whenever any book arrives, then scan only that pair quickly
    agg.subscribe(lambda b: (detector.on_book(b), detector.scan_pair(b.pair)))

    async def spawn_exchange(eid: str, use_ws: bool):
        if use_ws:
            await run_ws_exchange(eid, pairs, agg.on_book)
        else:
            await run_rest_exchange(eid, pairs, cfg.rest_poll_ms, agg.on_book)

    tasks = [asyncio.create_task(spawn_exchange(e["id"], bool(e.get("use_ws", False)))) for e in exs]

    # dashboard hooks
    def latest_fn(n: int):
        return latest[:n]

    def subscribe_fn(queue):
        # Register a subscriber; return an unsubscribe
        subs.append(queue)
        def unsub():
            subs.remove(queue)
        return unsub

    # broadcast to dashboard subscribers when an opp is published
    old_publish = publish_opp
    def publish_and_broadcast(opp: Opportunity):
        old_publish(opp)
        for q in list(subs):
            if not q.full():
                q.put_nowait(opp)
    detector.publish_opp = publish_and_broadcast  # swap in

    # run dashboard
    app = make_app(latest_fn, subscribe_fn)
    config = uvicorn.Config(app=app, host=cfg.dashboard_host, port=cfg.dashboard_port, log_level="info")
    server = uvicorn.Server(config)
    tasks.append(asyncio.create_task(server.serve()))

    # keep alive
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass

def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
