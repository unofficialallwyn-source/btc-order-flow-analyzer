"""Read-only trade tape aggregation and reversal signal detection."""
from dataclasses import dataclass, asdict
from collections import deque
from datetime import datetime, timezone
from statistics import mean
import math

def bucket(ts_us, seconds):
    return (int(ts_us)//1_000_000//seconds)*seconds

@dataclass(frozen=True)
class Trade:
    timestamp_us: int
    price: float
    contracts: float
    aggressor: str
    symbol: str = "BTCUSD"

    @classmethod
    def from_ws(cls, data):
        if data.get("type") != "trades":
            raise ValueError("not a trade")
        role = data.get("r")
        if role not in ("m", "t"):
            raise ValueError("unknown buyer role")
        size, price, ts = float(data["s"]), float(data["p"]), int(data["t"])
        if size <= 0 or price <= 0 or ts <= 0 or not math.isfinite(size) or not math.isfinite(price):
            raise ValueError("invalid trade")
        return cls(ts, price, size, "buy" if role == "t" else "sell", data["sy"])

@dataclass
class Bar:
    start: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    buy_volume: float = 0
    sell_volume: float = 0
    trades: int = 0

    @property
    def delta(self):
        return self.buy_volume - self.sell_volume

    def add(self, t):
        self.high = max(self.high, t.price)
        self.low = min(self.low, t.price)
        self.close = t.price
        self.volume += t.contracts
        if t.aggressor == "buy":
            self.buy_volume += t.contracts
        else:
            self.sell_volume += t.contracts
        self.trades += 1

    def serialize(self):
        return {**asdict(self), "delta": self.delta}

class TradeAggregator:
    def __init__(self, seconds=60):
        self.seconds, self.active, self.cvd, self.late_dropped = seconds, None, 0.0, 0

    def push(self, trade):
        start = bucket(trade.timestamp_us, self.seconds)
        out = []
        if self.active is not None and start < self.active.start:
            self.late_dropped += 1
            return out
        if self.active is not None and start > self.active.start:
            out = [self.active]
            self.active = None
        if self.active is None:
            self.active = Bar(start, trade.price, trade.price, trade.price, trade.price)
        self.active.add(trade)
        self.cvd += trade.contracts if trade.aggressor == "buy" else -trade.contracts
        return out

    def flush(self):
        out, self.active = self.active, None
        return out

@dataclass
class OHLCV:
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    @classmethod
    def parse(cls, row):
        return cls(**{k: int(row[k]) if k == "time" else float(row[k])
                      for k in ("time","open","high","low","close","volume")})

def reversal_signals(candles, lookback=20, threshold=2.0):
    """Confirmed NEXT 15-minute close; prevents look-ahead."""
    candles = sorted(candles, key=lambda x:x.time)
    signals = []
    for i in range(lookback, len(candles)-1):
        spike, nxt = candles[i], candles[i+1]
        avg = mean(c.volume for c in candles[i-lookback:i])
        if avg <= 0 or spike.volume / avg < threshold:
            continue
        is_bull = spike.close < spike.open and nxt.close > spike.high
        is_bear = spike.close > spike.open and nxt.close < spike.low
        if not (is_bull or is_bear):
            continue
        prior = candles[i-lookback:i]
        sweep = spike.low < min(c.low for c in prior) if is_bull else spike.high > max(c.high for c in prior)
        signals.append({"spike_start":spike.time,"confirmed_at":nxt.time+900,
                        "direction":"bullish" if is_bull else "bearish",
                        "spike_volume":spike.volume,"prior_avg_volume":avg,
                        "rvol":round(spike.volume/avg,3),
                        "spike_high":spike.high,"spike_low":spike.low,
                        "confirmation_close":nxt.close,"liquidity_sweep":sweep,
                        "five_min_shift":"not_evaluated"})
    return signals

def confirm_5m_shift(signal, candles_5m):
    """Simple breakout confirmation, not a full HH/HL structure classification."""
    spike_start, confirmed = signal["spike_start"], signal["confirmed_at"]
    window = [c for c in candles_5m if spike_start+900 <= c.time and c.time+300 <= confirmed]
    if len(window) != 3:
        return {**signal,"five_min_shift":"insufficient_data"}
    passed = (window[-1].close > signal["spike_high"] if signal["direction"]=="bullish"
              else window[-1].close < signal["spike_low"])
    return {**signal,"five_min_shift":"confirmed_breakout" if passed else "not_confirmed"}

def utc_day(ts):
    return datetime.fromtimestamp(ts,timezone.utc).strftime("%Y-%m-%d")
