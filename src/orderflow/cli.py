"""CLI for read-only collection, historical backfill and reversal research."""
import argparse
import asyncio
import json
import logging
import os
import time
import httpx
from .storage import ShardWriter
from .collector import Collector
from .core import OHLCV,reversal_signals,confirm_5m_shift

API="https://api.india.delta.exchange/v2/history/candles"
RES={"1m":60,"5m":300,"15m":900,"1h":3600}

def fetch_candles(symbol,resolution,start,end):
    step=RES[resolution]*1800
    out={}
    with httpx.Client(timeout=30,headers={"User-Agent":"btc-orderflow-research/1.0"}) as http:
        for lo in range(start,end,step):
            hi=min(end,lo+step-1)
            for attempt in range(5):
                try:
                    response=http.get(API,params={"symbol":symbol,"resolution":resolution,"start":lo,"end":hi})
                    response.raise_for_status()
                    body=response.json()
                    if body.get("success") is False:
                        raise RuntimeError(str(body))
                    for c in body["result"]:
                        out[int(c["time"])]=OHLCV.parse(c)
                    break
                except (httpx.HTTPError,ValueError,RuntimeError):
                    if attempt==4:
                        raise
                    time.sleep(min(30,2**attempt))
    return sorted(out.values(),key=lambda x:x.time)

def main():
    p=argparse.ArgumentParser(description="Delta India read-only order flow analyzer")
    p.add_argument("command",choices=["collect","analyze","backfill","retry-spool"])
    p.add_argument("--symbol",default=os.getenv("SYMBOL","BTCUSD"))
    p.add_argument("--start",type=int)
    p.add_argument("--end",type=int)
    p.add_argument("--local-dir",default=os.getenv("SPOOL_DIR","./spool"))
    p.add_argument("--azure-container",default=os.getenv("AZURE_CONTAINER","btc-orderflow"))
    p.add_argument("--flush-seconds",type=int,default=int(os.getenv("FLUSH_SECONDS","300")))
    p.add_argument("--book-sample-seconds",type=int,default=int(os.getenv("BOOK_SAMPLE_SECONDS","10")))
    p.add_argument("--no-book",action="store_true")
    p.add_argument("--local-only",action="store_true")
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO)
    writer=ShardWriter(args.local_dir,os.getenv("AZURE_STORAGE_CONNECTION_STRING",""),
                       args.azure_container,not args.local_only)
    if args.command=="collect":
        async def run():
            collector=Collector(writer,args.symbol,args.flush_seconds,args.book_sample_seconds,
                                include_book=not args.no_book)
            try:
                await collector.run()
            finally:
                bar=collector.aggregator.flush()
                if bar:
                    collector.bars.append(bar.serialize())
                collector.flush(force=True)
        asyncio.run(run())
    elif args.command=="retry-spool":
        print(json.dumps({"uploaded":writer.retry_spool()}))
    else:
        if args.start is None or args.end is None or args.end<=args.start:
            p.error("provide --start and --end UNIX seconds")
        if args.command=="backfill":
            for resolution in ("1m","5m","15m"):
                rows=fetch_candles(args.symbol,resolution,args.start,args.end)
                writer.write("historical/candles/"+resolution,[vars(x) for x in rows])
                print(resolution,len(rows))
            for resolution in ("5m","15m"):
                rows=fetch_candles("OI:"+args.symbol,resolution,args.start,args.end)
                writer.write("historical/oi/"+resolution,[vars(x) for x in rows])
                print("OI",resolution,len(rows))
        else:
            f15=fetch_candles(args.symbol,"15m",max(0,args.start-20*900),args.end)
            f5=fetch_candles(args.symbol,"5m",args.start,args.end)
            signals=[confirm_5m_shift(s,f5) for s in reversal_signals(f15)
                     if args.start<=s["spike_start"] and s["confirmed_at"]<=args.end]
            print(json.dumps(signals,indent=2))
            writer.write("signals",signals)

if __name__=="__main__":
    main()
