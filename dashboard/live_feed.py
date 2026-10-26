"""Independent read-only public Delta Exchange websocket cache for the dashboard."""
import asyncio
from collections import deque
from datetime import datetime, timezone
import json
import threading
import time
import websockets

URL="wss://public-socket.india.delta.exchange"

def normalize_trade(message):
    if message.get("type")!="trades" or message.get("sy")!="BTCUSD":
        return None
    try:
        price=float(message["p"]); size=float(message["s"]); role=message["r"]; ts=int(message["t"])
    except (TypeError,ValueError,KeyError):
        return None
    if price<=0 or size<=0 or role not in ("m","t") or ts<=0:
        return None
    return {"timestamp":ts/1_000_000,"price":price,"size":size,"side":"buy" if role=="t" else "sell"}

def normalize_book(message):
    if message.get("type")!="ob_l2" or message.get("sy")!="BTCUSD":
        return None
    try:
        bids=[[float(p),float(s)] for p,s in message["b"]]
        asks=[[float(p),float(s)] for p,s in message["a"]]
    except (ValueError,TypeError,KeyError):
        return None
    return {"bids":bids,"asks":asks,"timestamp":int(message.get("ts",0))/1_000_000}

class LiveFeed:
    def __init__(self):
        self.lock=threading.RLock()
        self.trades=deque(maxlen=150000)
        self.book=None
        self.status="starting"
        self.connected_at=None
        self.disconnections=0
        self.latest_trade_at=None
        self.thread=threading.Thread(target=self._thread,daemon=True,name="delta-btc-dashboard")
        self.thread.start()

    def _thread(self):
        asyncio.run(self._serve())

    async def _serve(self):
        retry=1
        while True:
            try:
                async with websockets.connect(URL,ping_interval=20,ping_timeout=20,max_size=5_000_000) as sock:
                    await sock.send(json.dumps({"type":"subscribe","payload":{"channels":[
                        {"name":"trades","symbols":["BTCUSD"]},
                        {"name":"ob_l2","symbols":["BTCUSD"]}
                    ]}}))
                    with self.lock:
                        self.status="connected"
                        self.connected_at=time.time()
                    retry=1
                    async for raw in sock:
                        message=json.loads(raw)
                        if not isinstance(message,dict):
                            continue
                        t=normalize_trade(message)
                        b=normalize_book(message)
                        with self.lock:
                            if t:
                                self.trades.append(t)
                                self.latest_trade_at=time.time()
                            if b:
                                self.book=b
            except Exception as exc:
                with self.lock:
                    self.status=f"reconnecting: {type(exc).__name__}"
                    self.disconnections+=1
            await asyncio.sleep(retry)
            retry=min(retry*2,60)

    def snapshot(self,seconds=3600):
        cutoff=time.time()-seconds
        with self.lock:
            trades=[t.copy() for t in self.trades if t["timestamp"]>=cutoff]
            book=None if self.book is None else {
                "bids":[level[:] for level in self.book["bids"]],
                "asks":[level[:] for level in self.book["asks"]],
                "timestamp":self.book["timestamp"]}
            return {"trades":trades,"book":book,"status":self.status,
                    "connected_at":self.connected_at,"latest_trade_at":self.latest_trade_at,
                    "disconnections":self.disconnections}
