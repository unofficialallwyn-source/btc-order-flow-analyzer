"""Read-only BTCUSD public trade tape / order-book websocket collector."""
import asyncio
import json
import logging
from datetime import datetime,timezone
import websockets
from .core import Trade,TradeAggregator
from .storage import ShardWriter

LOG=logging.getLogger(__name__)
ENDPOINT="wss://public-socket.india.delta.exchange"

class Collector:
    def __init__(self,writer:ShardWriter,symbol="BTCUSD",flush_seconds=300,
                 book_sample_seconds=10,max_records=20000,include_book=True):
        self.writer,self.symbol=writer,symbol
        self.flush_seconds,self.book_sample_seconds=flush_seconds,book_sample_seconds
        self.max_records,self.include_book=max_records,include_book
        self.trades,self.books,self.bars,self.status=[],[],[],[]
        self.aggregator=TradeAggregator(60)
        self.last_book_sample=0.0
        self.last_flush=asyncio.get_running_loop().time()

    def handle(self,msg):
        typ=msg.get("type")
        if typ=="trades" and msg.get("sy")==self.symbol:
            try:
                t=Trade.from_ws(msg)
            except (ValueError,KeyError,TypeError):
                return
            # Do not dedupe by timestamp/size: distinct matching fills can exist.
            self.trades.append({"ts_us":t.timestamp_us,"price":t.price,
                               "contracts":t.contracts,"aggressor":t.aggressor,"symbol":t.symbol})
            self.bars.extend(b.serialize() for b in self.aggregator.push(t))
        elif typ=="ob_l2" and self.include_book and msg.get("sy")==self.symbol:
            now=asyncio.get_running_loop().time()
            if now-self.last_book_sample>=self.book_sample_seconds:
                self.books.append({"received_at":datetime.now(timezone.utc).isoformat(),"message":msg})
                self.last_book_sample=now
        elif typ in ("error","system_status"):
            self.status.append({"at":datetime.now(timezone.utc).isoformat(),"data":msg})

    def flush(self,force=False):
        now=asyncio.get_running_loop().time()
        if not force and now-self.last_flush<self.flush_seconds and max(map(len,
                (self.trades,self.books,self.bars)))<self.max_records:
            return
        for name in ("trades","books","bars","status"):
            buf=getattr(self,name)
            if buf:
                self.writer.write(name,buf)
                buf.clear()
        self.last_flush=now

    async def run(self):
        failures=0
        while True:
            try:
                async with websockets.connect(ENDPOINT,ping_interval=25,ping_timeout=20,
                                              max_size=8_000_000) as ws:
                    failures=0
                    chans=[{"name":"trades","symbols":[self.symbol]}]
                    if self.include_book:
                        chans.append({"name":"ob_l2","symbols":[self.symbol]})
                    await ws.send(json.dumps({"type":"subscribe","payload":{"channels":chans}}))
                    await ws.send(json.dumps({"type":"enable_heartbeat"}))
                    LOG.info("connected to %s",self.symbol)
                    while True:
                        try:
                            raw=await asyncio.wait_for(ws.recv(),timeout=10)
                            msg=json.loads(raw)
                            if isinstance(msg,dict):
                                self.handle(msg)
                        except asyncio.TimeoutError:
                            pass
                        self.flush()
            except (OSError,websockets.exceptions.WebSocketException,asyncio.TimeoutError) as e:
                failures+=1
                LOG.warning("reconnecting after %s",e)
                try:
                    self.flush(force=True)
                except Exception:
                    LOG.exception("local spool flush failed")
                await asyncio.sleep(min(300,2**min(failures,7)))
