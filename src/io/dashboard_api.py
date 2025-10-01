from __future__ import annotations
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse, HTMLResponse
from typing import List
from core.types import Opportunity
import asyncio

def make_app(latest_fn, subscribe_fn):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return JSONResponse({"ok": True})

    @app.get("/opps/latest")
    async def latest(limit: int = 50):
        return [o.model_dump() for o in latest_fn(limit)]

    html = """
    <!doctype html><html><body>
    <h2>AUD ARB — Live Opportunities</h2>
    <pre id="log"></pre>
    <script>
      const log = document.getElementById('log');
      const ws = new WebSocket(`ws://${location.host}/stream`);
      ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        const s = `[${new Date(data.ts*1000).toISOString()}] ${data.pair}  BUY ${data.buy_ex} @ ${data.buy_price}  → SELL ${data.sell_ex} @ ${data.sell_price}  net_bps=${data.net_bps}  AUD=${data.profit_aud}\n`;
        log.textContent = s + log.textContent;
      }
    </script>
    </body></html>
    """

    @app.get("/")
    async def root():
        return HTMLResponse(html)

    @app.websocket("/stream")
    async def stream(ws: WebSocket):
        await ws.accept()
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        unsub = subscribe_fn(queue)
        try:
            while True:
                data = await queue.get()
                await ws.send_json(data.model_dump())
        except Exception:
            pass
        finally:
            unsub()
            await ws.close()

    return app
