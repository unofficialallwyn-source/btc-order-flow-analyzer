"""Pure analysis functions for real exchange aggressor-side trade flow."""
from collections import defaultdict
from datetime import datetime,timezone
from statistics import mean

def delta_bars(trades,minutes=1):
    buckets=defaultdict(lambda:{"buy":0.0,"sell":0.0,"count":0})
    seconds=minutes*60
    for t in trades:
        period=int(t["timestamp"]//seconds)*seconds
        item=buckets[period]
        item[t["side"]]+=t["size"]
        item["count"]+=1
    cvd=0.0
    result=[]
    for timestamp,record in sorted(buckets.items()):
        delta=record["buy"]-record["sell"]
        cvd+=delta
        result.append({"time":datetime.fromtimestamp(timestamp,timezone.utc),
                       **record,"delta":delta,"cvd":cvd})
    return result

def footprint(trades,price_step=5.0,minutes=15):
    if not trades:
        return []
    last=max(t["timestamp"] for t in trades)
    period=int(last//(minutes*60))*(minutes*60)
    values=defaultdict(lambda:{"buy":0.0,"sell":0.0})
    for t in trades:
        if t["timestamp"]<period:
            continue
        level=round(round(t["price"]/price_step)*price_step,6)
        values[level][t["side"]]+=t["size"]
    return [{"price":p,"buy":v["buy"],"sell":v["sell"],
             "delta":v["buy"]-v["sell"]} for p,v in sorted(values.items(),reverse=True)]

def book_imbalance(book,levels=10):
    if not book:
        return None
    bids=sum(level[1] for level in book["bids"][:levels])
    asks=sum(level[1] for level in book["asks"][:levels])
    return (bids-asks)/(bids+asks) if (bids+asks)>0 else None

def relative_volume(candles,lookback=20):
    if len(candles)<lookback+1:
        return None
    avg=mean(c["volume"] for c in candles[-lookback-1:-1])
    return candles[-1]["volume"]/avg if avg>0 else None

def classify_spike(candles,lookback=20,threshold=2.0):
    """Only classify completed candles; caller must omit currently forming candle."""
    if len(candles)<lookback+2:
        return []
    out=[]
    for i in range(lookback,len(candles)-1):
        candle, nxt=candles[i:i+2]
        avg=mean(c["volume"] for c in candles[i-lookback:i])
        if not avg or candle["volume"]<threshold*avg:
            continue
        bullish=candle["close"]<candle["open"] and nxt["close"]>candle["high"]
        bearish=candle["close"]>candle["open"] and nxt["close"]<candle["low"]
        if bullish or bearish:
            out.append({"time":candle["time"],"confirmed":nxt["time"],
                        "direction":"bullish" if bullish else "bearish",
                        "rvol":candle["volume"]/avg,"level":candle["high"] if bullish else candle["low"]})
    return out
