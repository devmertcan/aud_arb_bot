from __future__ import annotations
import asyncio, yaml
from pathlib import Path
from decimal import Decimal as D
from core.types import RuntimeConfig, BestBook, Opportunity, TriOpportunity
from core.fees import Fees
from core.utils import now_s
from md.aggregator import Aggregator
from md.ws_client import run_ws_exchange
from md.rest_client import run_rest_exchange
from src.io.csv_sink import CsvSink
from arb.engine import Detector
from arb.triangular import TriDetector
from src.io.dashboard_api import make_app
import uvicorn

import ccxt
try:
    import ccxt.pro as ccxtpro
except Exception:
    ccxtpro = None

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
OUT = ROOT.parent / "out"

def load_yaml(p: Path): 
    return yaml.safe_load(p.read_text())

def load_runtime() -> RuntimeConfig:
    d = load_yaml(CONFIG / "runtime.yml")["runtime"]
    d["max_trade_aud"] = D(str(d["max_trade_aud"]))
    d["min_profit_bps_after_fees"] = D(str(d["min_profit_bps_after_fees"]))
    d["slippage_bps_buffer"] = D(str(d["slippage_bps_buffer"]))
    d["tri_start_aud"] = D(str(d["tri_start_aud"]))
    return RuntimeConfig(**d)

async def run():
    pairs = load_yaml(CONFIG / "pairs.yml")["pairs"]
    exs = [e for e in load_yaml(CONFIG / "exchanges.yml")["exchanges"] if e.get("enabled")]
    fees = Fees(CONFIG / "fees.yml")
    cfg = load_runtime()

    agg = Aggregator()
    sink = CsvSink(OUT)

    # Lists for dashboard "latest"
    latest: list[dict] = []
    subs: list[asyncio.Queue] = []

    # --- publishers (to CSV + dashboard) ---
    def broadcast(payload: dict):
        # keep a mixed rolling list of last 500 events
        latest.insert(0, payload)
        if len(latest) > 500:
            latest.pop()
        # non-blocking broadcast
        for q in list(subs):
            if not q.full():
                q.put_nowait(payload)

    def publish_cex(o: Opportunity):
        sink.write_opp(o)
        broadcast(o.model_dump())

    def publish_tri(t: TriOpportunity):
        sink.write_tri(t)
        broadcast(t.model_dump())

    # --- detectors ---
    cex_detector = Detector(fees, cfg, publish_cex)
    tri_detector = TriDetector(fees, cfg, publish_tri)

    # write all top-of-book snapshots + feed detectors
    def on_book(b: BestBook):
        sink.write_tob(b)
        cex_detector.on_book(b)
        tri_detector.on_book(b)
        # fast per-pair CEX scan
        cex_detector.scan_pair(b.pair)
        # fast per-exchange TRI scan
        tri_detector.scan_exchange(b.exchange, start_aud=cfg.tri_start_aud)

    agg.subscribe(on_book)

    async def spawn_exchange(eid: str, use_ws: bool, ob_limit: int | None):
        # Decide capabilities
        ws_supported = bool(ccxtpro) and hasattr(ccxtpro, eid)
        rest_supported = hasattr(ccxt, eid)

        if use_ws and ws_supported:
            print(f"[INFO] {eid}: using WebSocket via ccxt.pro")
            try:
                await run_ws_exchange(eid, pairs, agg.on_book, ob_limit=ob_limit)
                return
            except Exception as e:
                print(f"[WARN] {eid}: WS failed ({e}); falling back to REST…")

        if rest_supported:
            print(f"[INFO] {eid}: using REST via ccxt")
            await run_rest_exchange(eid, pairs, cfg.rest_poll_ms, agg.on_book, ob_limit=ob_limit)
        else:
            print(f"[WARN] {eid}: not supported by CCXT/ccxt.pro — skipping")

    tasks = [asyncio.create_task(spawn_exchange(e["id"], bool(e.get("use_ws", False)), e.get("ob_limit"))) for e in exs]

    # dashboard hooks
    def latest_fn(n: int):
        return latest[:n]

    def subscribe_fn(queue: asyncio.Queue):
        subs.append(queue)
        def unsub():
            try:
                subs.remove(queue)
            except ValueError:
                pass
        return unsub

    app = make_app(latest_fn, subscribe_fn)
    config = uvicorn.Config(app=app, host=cfg.dashboard_host, port=cfg.dashboard_port, log_level="info")
    server = uvicorn.Server(config)
    tasks.append(asyncio.create_task(server.serve()))

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
