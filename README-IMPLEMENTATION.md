# BTC Order Flow Analyzer

Read-only Delta Exchange India BTCUSD research application.

## Commands
- `orderflow collect` — records maker/taker-classified public trade tape, 1m OHLCV with delta, and sampled ob_l2 depth.
- `orderflow analyze --start EPOCH --end EPOCH` — non-lookahead 15m relative-volume reversal signals with basic 5m breakout validation.
- `orderflow backfill --start EPOCH --end EPOCH` — historical OHLCV and OI, NOT historical tick trades or book states.
- `orderflow retry-spool` — retries locally spooled compressed JSONL shards.

## Getting started
`cp .env.example .env`
Set AZURE_STORAGE_CONNECTION_STRING if uploads are needed. Create the Azure blob container `btc-orderflow` beforehand. Run `docker compose up --build -d`.
Or run `pip install -e '.[dev]'` then `pytest -q` and `orderflow collect --local-only`.

## Cost controls
Data batched at 5 minutes, gzip compresslevel=6, only sample order book every 10 seconds; local persistent spool. Limit lifecycle by Azure Storage lifecycle rules; suggested raw trades 30d, books 7d, aggregate bars and signals 365d. Lifecycle rules must be configured on the Azure account separately. No auto-deployment or Azure resource creation.

## Research caveats
Public websocket requires long-lived host; Azure Blob is a storage destination, not a collector runtime. Reconnect outages cause irrevocable trade-tape gaps; evaluate data completeness before backtests. Order book snapshots do not reconstruct hidden liquidity or historical order book. This application never authenticates to Delta trading endpoints or places orders. Signal outcomes are not guaranteed. Historical data fetch must be validated against the live production API.
