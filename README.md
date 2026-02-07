# Interactive Brokers TWS API Demo

## Prerequisites

1. **TWS or IB Gateway** must be running on your machine.
   - Download from: https://www.interactivebrokers.com/en/trading/tws.php
   - Enable API connections: TWS → Edit → Global Configuration → API → Settings
     - Check "Enable ActiveX and Socket Clients"
     - Set Socket port to `7497` (paper) or `7496` (live)
     - Uncheck "Read-Only API" if you want to place orders

2. **Python 3.7+** is required.

## Setup

```bash
pip install -r requirements.txt
```

## Running the Demos

```bash
# Full demo — connects to TWS and runs all examples
python tws_api_demo.py

# Each section can also be toggled on/off inside the script
```

## What's Covered

| Section | What it demonstrates |
|---|---|
| Connection | Connect/disconnect to TWS or IB Gateway |
| Contract Definitions | Define stocks, forex, futures, options |
| Market Data (Live) | Stream real-time quotes (bid/ask/last) |
| Market Data (Snapshot) | One-shot quote request |
| Historical Data | OHLCV bars (candles) for any timeframe |
| Fundamental Data | Financial summaries and ratios |
| Account & Portfolio | Account balances, margin, open positions |
| Order Placement | Market, limit, stop, bracket, and OCA orders |
| Order Management | Modify and cancel open orders |
| Scanner | Market scanners (top gainers, most active, etc.) |
| Options Chains | Fetch available strikes/expirations |
| Real-time Bars | 5-second live candle streaming |
| News | Headlines and article bodies |
| Contract Search | Search for contracts by name/symbol |
