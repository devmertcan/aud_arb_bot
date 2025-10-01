from __future__ import annotations
from fastapi import FastAPI, WebSocket
from fastapi.responses import JSONResponse, HTMLResponse
import asyncio

def make_app(latest_fn, subscribe_fn):
    app = FastAPI()

    @app.get("/health")
    async def health():
        return JSONResponse({"ok": True})

    @app.get("/opps/latest")
    async def latest(limit: int = 50):
        # returns a mixed list of cex and tri dicts
        return [o for o in latest_fn(limit)]

    html = """
    <!doctype html><html><body>
    <h2>AUD ARB — Live Opportunities</h2>
    <pre id="log"></pre>
    <script>
      const log = document.getElementById('log');
      const ws = new WebSocket(`ws://${location.host}/stream`);
      function line(d){
        if(d.kind === 'tri'){
          return `[${new Date(d.ts*1000).toISOString()}] TRI ${d.exchange}  ${d.path.join('->')}  net_bps=${d.net_bps}  AUD=${d.profit_aud}  conf=${d.confidence.toFixed(2)}\\n`;
        } else {
          return `[${new Date(d.ts*1000).toISOString()}] CEX ${d.pair}  BUY ${d.buy_ex} @ ${d.buy_price}  → SELL ${d.sell_ex} @ ${d.sell_price}  net_bps=${d.net_bps}  AUD=${d.profit_aud}  conf=${d.confidence.toFixed(2)}\\n`;
        }
      }
      ws.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        log.textContent = line(data) + log.textContent;
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
                await ws.send_json(data)
        except Exception:
            pass
        finally:
            unsub()
            await ws.close()

    return app
