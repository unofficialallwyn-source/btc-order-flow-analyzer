from orderflow.core import Trade,TradeAggregator,OHLCV,reversal_signals,confirm_5m_shift
from orderflow.storage import ShardWriter
import gzip

def test_aggressors():
    base={"type":"trades","sy":"BTCUSD","t":1000000000,"p":"80000","s":5}
    assert Trade.from_ws({**base,"r":"t"}).aggressor=="buy"
    assert Trade.from_ws({**base,"r":"m"}).aggressor=="sell"

def test_aggregation_delta_and_late_trade():
    a=TradeAggregator(60)
    a.push(Trade(61000000,100,2,"buy"))
    a.push(Trade(62000000,99,1,"sell"))
    bar=a.push(Trade(121000000,101,3,"buy"))[0]
    assert bar.delta==1 and bar.volume==3 and bar.low==99 and bar.high==100
    assert a.cvd==4
    a.push(Trade(62000000,99,1,"buy"))
    assert a.late_dropped==1

def test_reversal_and_no_lookahead():
    candles=[OHLCV(i*900,100,102,98,100.5,100) for i in range(20)]
    spike=OHLCV(20*900,101,102,95,96,300)
    confirm=OHLCV(21*900,96,105,96,104,150)
    assert reversal_signals(candles+[spike])==[]
    signal=reversal_signals(candles+[spike,confirm])[0]
    assert signal["rvol"]==3 and signal["liquidity_sweep"] is True
    five=[OHLCV(21*900+j*300,100,105,99,103,25) for j in range(3)]
    assert confirm_5m_shift(signal,five)["five_min_shift"]=="confirmed_breakout"

def test_local_compressed_storage(tmp_path):
    s=ShardWriter(str(tmp_path))
    key=s.write("trades",[{"test":1}])
    with gzip.open(tmp_path/key,"rt") as f:
        assert f.read().strip()=='{"test":1}'
