# BTCUSD Order-Flow Dashboard

Local, read-only chart for Delta Exchange India BTCUSD.

## Run

```bash
cd dashboard
python -m venv .venv
# Activate the virtualenv for your shell
pip install -r requirements.txt
streamlit run app.py
```

Opens at http://localhost:8501. No API key, trading permissions, or Azure resources required.

## Panels
- 1m / 5m / 15m / 1h public Delta OHLCV candles and volume
- Actual taker-signed trade delta and rolling-session CVD, from the moment dashboard connects
- 15m price-level buy/sell footprint aggregated at selectable price bins
- L2 top-15 bid/ask snapshot and 10-level book imbalance
- Confirmed 15m 2x RVOL reversal screening (uses next *closed* candle only)
- Disconnect and stale-data warnings

## Scope and limitations
The dashboard maintains a bounded in-memory tape and is intended for **local**, single-server operation. It cannot fill missed trades during outages, and a rerun/restart resets CVD. It does not merge historical candles with unavailable historical aggressor trades. CVD comparisons must stay within a contiguous capture session. Order-book snapshots are NOT historical liquidity heatmaps, and the footprint represents ONLY tape retained in memory. For durable history run the existing collector separately; Azure cost stays zero for dashboard-only local usage. Do not expose the Streamlit server to the public internet without authentication. The app never calls private Delta endpoints or places orders.

## Official feed
https://docs.delta.exchange/ — Public Websocket `trades` and `ob_l2` channels.
