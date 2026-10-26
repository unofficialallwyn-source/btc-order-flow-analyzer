import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from analytics import delta_bars,footprint,book_imbalance,classify_spike
from live_feed import normalize_trade,normalize_book

def test_trade_role():
    x={"type":"trades","sy":"BTCUSD","p":"100","s":2,"r":"t","t":1000000000}
    assert normalize_trade(x)["side"]=="buy"
    assert normalize_trade({**x,"r":"m"})["side"]=="sell"

def test_book_format():
    x={"type":"ob_l2","sy":"BTCUSD","a":[["101","4"]],"b":[["100","6"]],"ts":1000000}
    b=normalize_book(x)
    assert book_imbalance(b)==.2

def test_true_delta_and_footprint():
    t=[{"timestamp":900,"price":100,"size":5,"side":"buy"},
       {"timestamp":902,"price":99,"size":3,"side":"sell"}]
    assert delta_bars(t)[0]["delta"]==2
    assert sum(x["delta"] for x in footprint(t,1.0))==2

def test_signal_needs_next_closed_candle():
    c=[{"time":i*900,"open":100,"high":105,"low":95,"close":100,"volume":100} for i in range(20)]
    spike={"time":18000,"open":101,"high":103,"low":90,"close":92,"volume":300}
    nxt={"time":18900,"open":92,"high":110,"low":91,"close":106,"volume":150}
    assert not classify_spike(c+[spike])
    assert classify_spike(c+[spike,nxt])[0]["direction"]=="bullish"
