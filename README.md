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
# Optional launcher (single entrypoint)
python run_demo.py --demo basic
python run_demo.py --demo advanced
python run_demo.py --demo uncovered
python run_demo.py --demo valuation -- --ticker AAPL
python run_demo.py --demo dashboard -- --ticker AAPL

# Full demo — connects to TWS and runs all examples
python tws_api_demo.py

# Advanced demo — richer, event-driven workflows
python tws_api_advanced_demo.py

# Third demo — APIs not covered by the first two
python tws_api_uncovered_demo.py

# Value-investor model — valuation + sentiment for one ticker
python value_investor_model.py --ticker AAPL

# Enhanced Buffett/Munger dashboard (detailed)
python buffett_munger_dashboard.py --ticker AAPL

# Each section can also be toggled on/off inside the script
```

## Advanced Demo Highlights

`tws_api_advanced_demo.py` demonstrates more advanced API patterns:

- Event-driven streaming via `pendingTickersEvent`
- Historical + real-time bar integration
- Option chain discovery via `reqSecDefOptParams`
- Multi-leg combo (`BAG`) contract construction
- Bracket and OCA order setup patterns (safe/non-transmitting)
- Scanner-to-contract resolution pipeline
- News provider discovery + historical headlines

## Third Demo Highlights (Uncovered APIs)

`tws_api_uncovered_demo.py` covers additional APIs not shown in demos 1/2:

- Market structure APIs: `reqMktDepthExchanges`, `reqMarketRule`, `reqSmartComponents`
- Fundamental/reference APIs: `reqFundamentalData`, `reqHeadTimeStamp`, `reqHistogramData`
- News article body retrieval: `reqNewsArticle`
- Execution reporting APIs: `reqExecutions`, `reqCompletedOrders`
- Per-position real-time PnL: `reqPnLSingle`
- Proper what-if margin/commission preview: `whatIfOrder`

## Value Investor Model

`value_investor_model.py` runs a single-ticker analysis pipeline:

- Pulls price, fundamental snapshot, and 5-year history
- Parses key valuation fields (EPS, book value, ROE, leverage, multiples)
- Computes news sentiment from headlines + article bodies
- Blends valuation models (Graham, earnings-power, book-value anchor)
- Outputs intrinsic value, margin of safety, and recommendation

## Buffett/Munger Dashboard

`buffett_munger_dashboard.py` expands to a detailed value-investor dashboard:

- Buffett-style quality checks (ROE, ROIC, margins, leverage, liquidity)
- Multi-model intrinsic value (`graham`, `earnings_power`, `owner_earnings`, `book_anchor`)
- Munger mental-model scorecard (moat, predictability, inversion/risk, checklist)
- Sentiment + narrative risk scan from IB headlines/articles
- Final recommendation with explicit margin-of-safety framing

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
