"""Non-predictive, evidence-weighted quality evaluation of confirmed 15m reversals.

Never infer historic tape delta from OHLCV. Points requiring missing or discontinuous
trade tape remain UNAVAILABLE rather than being scored zero or assumed positive.
"""
from datetime import datetime, timezone
from statistics import mean

def evaluate_signal(signal, candles_15m, candles_5m, trades, connected_at, disconnections=0,
                    stale=False, now=None):
    start=int(signal["time"])
    confirmed_start=int(signal["confirmed"])
    end=confirmed_start+900
    direction=signal["direction"]
    aligned=1 if direction=="bullish" else -1
    candles_15m=sorted(candles_15m,key=lambda c:c["time"])
    candles_5m=sorted(candles_5m,key=lambda c:c["time"])
    past=next((c for c in candles_15m if c["time"]==start),None)
    follow=next((c for c in candles_15m if c["time"]==confirmed_start),None)
    scores=[]
    def add(name,points,max_points,detail,available=True):
        scores.append({"component":name,"points":points if available else None,
                       "max":max_points,"detail":detail,"available":available})
    if past is None or follow is None or (now is not None and now<end):
        return {"status":"pending","components":[],"score":None,"possible":100,
                "reason":"Confirmation candle not closed or historical bars unavailable."}
    # 30: cross candle reclaim measured after confirmation close
    reclaim=(follow["close"]>past["high"] if aligned==1 else follow["close"]<past["low"])
    add("15m confirmed reclaim",30 if reclaim else 0,30,
        "Next completed 15m candle reclaimed spike extreme" if reclaim else "No confirmed extreme reclaim")
    # 20: measured RVOL on the original 15m candle
    rvol=float(signal["rvol"])
    add("15m relative volume",20 if rvol>=2.5 else (15 if rvol>=2 else 0),20,
        f"Spike RVOL {rvol:.2f}x")
    # 20: exact three 5m candles constituting the confirming 15m interval
    segment=[c for c in candles_5m if confirmed_start<=c["time"]<end]
    valid=(len(segment)==3 and [c["time"] for c in segment]==
           [confirmed_start,confirmed_start+300,confirmed_start+600])
    if valid:
        final=segment[-1]["close"]
        structure=final>past["high"] if aligned==1 else final<past["low"]
        add("5m breakout confirmation",20 if structure else 0,20,
            "5m breakout aligned with reversal" if structure else "No 5m close beyond spike extreme")
    else:
        add("5m breakout confirmation",None,20,"Missing 5m candles",False)
    # 30: only count real executions when the *entire* confirming 15m interval is collected,
    # connection predates the interval, and there have been no reconnects.
    window=sorted((t for t in trades if confirmed_start<=t["timestamp"]<end),
                  key=lambda t:t["timestamp"])
    complete=(connected_at is not None and connected_at<=confirmed_start
              and disconnections==0 and not stale and len(window)>=2
              and window[0]["timestamp"]<=confirmed_start+30
              and window[-1]["timestamp"]>=end-30)
    if complete:
        buy=sum(float(t["size"]) for t in window if t["side"]=="buy")
        sell=sum(float(t["size"]) for t in window if t["side"]=="sell")
        signed=(buy-sell)*aligned
        total=buy+sell
        ratio=signed/total if total else 0
        add("Actual 15m aggressor delta",30 if ratio>=.1 else (15 if ratio>0 else 0),30,
            f"Signed delta {signed:+,.0f} contracts ({ratio:+.1%} of volume)")
    else:
        add("Actual 15m aggressor delta",None,30,
            "Unavailable: full, gap-free 15m trade tape not verified",False)
    possible=sum(c["max"] for c in scores if c["available"])
    points=sum(c["points"] for c in scores if c["available"])
    full=possible==100
    return {"status":"complete" if full else "partial",
            "score":points,"possible":possible,
            "percentage":round(100*points/possible,1) if possible else None,
            "components":scores,
            "reason":"Full evidence" if full else "Partial evidence: missing inputs excluded, not inferred"}
