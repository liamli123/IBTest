"""
===============================================================================
 Interactive Brokers TWS API Demo
===============================================================================

This script demonstrates the major capabilities of the IB TWS API using
the `ib_insync` library — a high-level, Pythonic wrapper around the
official Interactive Brokers API.

PREREQUISITES:
  1. TWS (Trader Workstation) or IB Gateway must be running.
  2. API connections must be enabled in TWS:
       Edit → Global Configuration → API → Settings
       - Check "Enable ActiveX and Socket Clients"
       - Socket port: 7497 (paper trading) or 7496 (live trading)
  3. Install dependencies:  pip install -r requirements.txt

IMPORTANT:
  - This demo uses a PAPER TRADING port (7497) by default.
  - Placing orders on a live account will use REAL MONEY.
  - Always test on paper first.

Usage:
  python tws_api_demo.py
===============================================================================
"""

import time
from datetime import datetime, timedelta

from ib_insync import (
    IB,
    Stock,
    Forex,
    Future,
    Option,
    Contract,
    MarketOrder,
    LimitOrder,
    StopOrder,
    ScannerSubscription,
    util,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TWS_HOST = "127.0.0.1"   # TWS/Gateway runs locally
TWS_PORT = 7497           # 7497 = paper trading, 7496 = live trading
CLIENT_ID = 1             # Unique ID for this API client (use different IDs
                          # if running multiple scripts simultaneously)


# ============================================================================
# SECTION 1: CONNECTION
# ============================================================================
def demo_connection(ib: IB):
    """
    Connect to TWS / IB Gateway.

    The IB class is the main entry point. It manages:
      - The TCP socket connection to TWS
      - Request/response message handling
      - An internal event loop for async operations

    Parameters:
      host     — IP address where TWS is running (usually localhost)
      port     — API socket port configured in TWS
      clientId — Unique integer; TWS allows multiple simultaneous clients
    """
    print("\n" + "=" * 70)
    print("SECTION 1: CONNECTING TO TWS")
    print("=" * 70)

    ib.connect(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)

    # After connecting, we can check the connection status
    print(f"  Connected:        {ib.isConnected()}")
    print(f"  TWS Server Time:  {ib.reqCurrentTime()}")

    # The managed accounts list shows which accounts this login can access
    print(f"  Managed Accounts: {ib.managedAccounts()}")

    return ib


# ============================================================================
# SECTION 2: DEFINING CONTRACTS
# ============================================================================
def demo_contracts():
    """
    A 'Contract' tells IB which instrument you want to trade or get data for.

    Every request (market data, orders, etc.) requires a contract object.
    The key fields are:
      - symbol:    Ticker symbol (e.g. 'AAPL')
      - secType:   Security type — 'STK', 'FX', 'FUT', 'OPT', etc.
      - exchange:  Exchange — 'SMART' for best routing, or specific like 'NASDAQ'
      - currency:  Currency the instrument is denominated in
    """
    print("\n" + "=" * 70)
    print("SECTION 2: DEFINING CONTRACTS")
    print("=" * 70)

    # --- US Stock ---
    # SMART exchange = IB's Smart Order Routing (finds best price across exchanges)
    apple = Stock("AAPL", "SMART", "USD")
    print(f"  Stock:   {apple}")

    # --- Forex pair ---
    # Forex contracts use the IDEALPRO exchange
    eurusd = Forex("EURUSD")
    print(f"  Forex:   {eurusd}")

    # --- Futures ---
    # Futures need lastTradeDateOrContractMonth to identify the specific contract
    es_future = Future("ES", "202503", "CME")  # E-mini S&P 500, March 2025
    print(f"  Future:  {es_future}")

    # --- Options ---
    # Options need: expiry, strike, right ('C' = call, 'P' = put)
    aapl_call = Option("AAPL", "20250321", 200, "C", "SMART")
    print(f"  Option:  {aapl_call}")

    # --- Generic contract by conId ---
    # Every instrument has a unique contract ID (conId). If you know it,
    # you can create a contract with just the conId:
    contract_by_id = Contract(conId=265598)  # This is AAPL
    print(f"  By ID:   {contract_by_id}")

    return apple, eurusd, es_future, aapl_call


# ============================================================================
# SECTION 3: CONTRACT DETAILS & SEARCH
# ============================================================================
def demo_contract_details(ib: IB, contract):
    """
    reqContractDetails() returns full information about a contract:
      - Full name, valid exchanges, trading hours
      - Minimum tick size, multiplier
      - Industry, category, subcategory
      - Supported order types

    This is also how you VALIDATE a contract before using it.
    If the contract is ambiguous or invalid, IB will tell you.
    """
    print("\n" + "=" * 70)
    print("SECTION 3: CONTRACT DETAILS & SEARCH")
    print("=" * 70)

    # Qualify the contract — this fills in missing fields (conId, exchange, etc.)
    # and verifies the contract exists at IB
    ib.qualifyContracts(contract)
    print(f"  Qualified contract: {contract}")
    print(f"  conId:              {contract.conId}")

    # Get full contract details
    details_list = ib.reqContractDetails(contract)
    if details_list:
        details = details_list[0]
        print(f"  Long Name:          {details.longName}")
        print(f"  Industry:           {details.industry}")
        print(f"  Category:           {details.category}")
        print(f"  Min Tick:           {details.minTick}")
        print(f"  Valid Exchanges:    {details.validExchanges}")

    # --- Matching Symbols (search by text) ---
    # Useful for finding the right contract when you only know a partial name
    matches = ib.reqMatchingSymbols("Tesla")
    if matches:
        print(f"\n  Search for 'Tesla' returned {len(matches)} results:")
        for m in matches[:3]:  # Show first 3
            print(f"    {m.contract.symbol} — {m.contract.secType} — "
                  f"{m.contract.primaryExchange}")


# ============================================================================
# SECTION 4: LIVE MARKET DATA (Streaming)
# ============================================================================
def demo_live_market_data(ib: IB, contract):
    """
    reqMktData() streams real-time market data (bid, ask, last, volume, etc.).

    The returned Ticker object updates automatically as new ticks arrive.
    Generic tick types can request additional data:
      - 100: Option volume
      - 101: Option open interest
      - 104: Historical volatility
      - 106: Implied volatility
      - 162: Index future premium
      - 165: Misc stats (avg volume, etc.)
      - 221: Mark price
      - 233: RTVolume (every trade in real time)
      - 236: Shortable shares
      - 258: Fundamental ratios

    NOTE: Live market data requires data subscriptions in your IB account.
          If you don't have them, use delayed data (see below).
    """
    print("\n" + "=" * 70)
    print("SECTION 4: LIVE MARKET DATA (Streaming)")
    print("=" * 70)

    # Request delayed data if you don't have live market data subscriptions.
    # Comment this out if you DO have live data.
    ib.reqMarketDataType(3)  # 1=Live, 2=Frozen, 3=Delayed, 4=Delayed-Frozen

    # Start streaming market data
    ticker = ib.reqMktData(contract, genericTickList="", snapshot=False)

    # Give it a moment to receive the first ticks
    ib.sleep(2)

    print(f"  Symbol:     {contract.symbol}")
    print(f"  Bid:        {ticker.bid}")
    print(f"  Ask:        {ticker.ask}")
    print(f"  Last:       {ticker.last}")
    print(f"  Volume:     {ticker.volume}")
    print(f"  High:       {ticker.high}")
    print(f"  Low:        {ticker.low}")
    print(f"  Close:      {ticker.close}")

    # Cancel the streaming data when done to free up the data line.
    # IB limits the number of simultaneous streaming requests (typically 100).
    ib.cancelMktData(contract)


# ============================================================================
# SECTION 5: MARKET DATA SNAPSHOT
# ============================================================================
def demo_snapshot(ib: IB, contract):
    """
    A snapshot requests a ONE-TIME quote instead of continuous streaming.

    Useful when you just need the current price without ongoing updates.
    Requires the 'snapshot' market data permission in your IB account,
    or use delayed data type (3).
    """
    print("\n" + "=" * 70)
    print("SECTION 5: MARKET DATA SNAPSHOT")
    print("=" * 70)

    ib.reqMarketDataType(3)  # Delayed data

    # snapshot=True gets a single quote and auto-cancels
    ticker = ib.reqMktData(contract, snapshot=True)
    ib.sleep(2)

    print(f"  {contract.symbol} snapshot — "
          f"Bid: {ticker.bid}, Ask: {ticker.ask}, Last: {ticker.last}")


# ============================================================================
# SECTION 6: HISTORICAL DATA
# ============================================================================
def demo_historical_data(ib: IB, contract):
    """
    reqHistoricalData() returns OHLCV bars (candles) for any timeframe.

    Parameters:
      endDateTime   — End of the data range ('' = now)
      durationStr   — How far back: '1 D', '1 W', '1 M', '1 Y', '30 D', etc.
      barSizeSetting— Bar size: '1 min', '5 mins', '15 mins', '1 hour',
                       '1 day', '1 week', '1 month'
      whatToShow    — Data type:
                       'TRADES'        — Trade prices (most common for stocks)
                       'MIDPOINT'      — Average of bid/ask
                       'BID'           — Bid prices
                       'ASK'           — Ask prices
                       'ADJUSTED_LAST' — Corporate-action-adjusted prices
                       'HISTORICAL_VOLATILITY'
                       'OPTION_IMPLIED_VOLATILITY'
      useRTH        — 1 = Regular Trading Hours only, 0 = include extended hours

    IB has pacing limitations:
      - Max 60 requests in 10 minutes
      - The amount of data you can request depends on bar size
        (e.g., 1-min bars go back ~6 months, daily bars go back years)
    """
    print("\n" + "=" * 70)
    print("SECTION 6: HISTORICAL DATA")
    print("=" * 70)

    # Get 30 days of daily bars
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",          # '' means "up to now"
        durationStr="30 D",      # 30 days of data
        barSizeSetting="1 day",  # Daily candles
        whatToShow="TRADES",     # Trade prices
        useRTH=True,             # Regular Trading Hours only
        formatDate=1,            # 1 = yyyyMMdd format, 2 = epoch seconds
    )

    if bars:
        print(f"  Received {len(bars)} daily bars for {contract.symbol}")
        print(f"  {'Date':<12} {'Open':>8} {'High':>8} {'Low':>8} "
              f"{'Close':>8} {'Volume':>10}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*8} {'-'*8} {'-'*10}")

        # Show the last 5 bars
        for bar in bars[-5:]:
            print(f"  {str(bar.date):<12} {bar.open:>8.2f} {bar.high:>8.2f} "
                  f"{bar.low:>8.2f} {bar.close:>8.2f} {bar.volume:>10}")

        # Convert to a pandas DataFrame for further analysis
        df = util.df(bars)
        print(f"\n  As DataFrame:\n{df.tail()}")
    else:
        print("  No historical data returned (check market data subscriptions)")


# ============================================================================
# SECTION 7: ACCOUNT & PORTFOLIO
# ============================================================================
def demo_account_portfolio(ib: IB):
    """
    Account and portfolio information:

    - accountSummary()  — Key financial metrics (net liquidation, buying power, etc.)
    - accountValues()   — Detailed account values (cash, margin, P&L, etc.)
    - portfolio()       — Current open positions with market value and P&L
    - positions()       — Simplified position list across all accounts

    These update automatically once requested.
    """
    print("\n" + "=" * 70)
    print("SECTION 7: ACCOUNT & PORTFOLIO")
    print("=" * 70)

    # --- Account Summary ---
    # Tags you can request (or 'All' for everything):
    #   NetLiquidation, TotalCashValue, BuyingPower, GrossPositionValue,
    #   MaintMarginReq, AvailableFunds, ExcessLiquidity, etc.
    summary = ib.accountSummary()
    print("  Account Summary (selected fields):")
    for item in summary:
        if item.tag in ("NetLiquidation", "TotalCashValue", "BuyingPower",
                        "MaintMarginReq"):
            print(f"    {item.tag:<25} {item.value:>15} {item.currency}")

    # --- Portfolio (open positions) ---
    portfolio = ib.portfolio()
    print(f"\n  Open Positions: {len(portfolio)}")
    for pos in portfolio[:5]:  # Show up to 5 positions
        print(f"    {pos.contract.symbol:<8} "
              f"Qty: {pos.position:>8} "
              f"Avg Cost: {pos.averageCost:>10.2f} "
              f"Market Value: {pos.marketValue:>12.2f} "
              f"Unrealized P&L: {pos.unrealizedPNL:>10.2f}")

    # --- Positions (simpler, across all accounts) ---
    positions = ib.positions()
    print(f"\n  Total positions across all accounts: {len(positions)}")


# ============================================================================
# SECTION 8: PLACING ORDERS
# ============================================================================
def demo_orders(ib: IB, contract):
    """
    Order types supported by IB TWS API:

    Basic:
      - MarketOrder(action, quantity)   — Execute immediately at market price
      - LimitOrder(action, qty, price)  — Execute at specified price or better
      - StopOrder(action, qty, price)   — Becomes market order when stop price hit

    Advanced:
      - StopLimitOrder    — Stop that becomes a limit order
      - TrailingStopOrder — Stop that trails the market by a fixed amount
      - BracketOrder      — Entry + take-profit + stop-loss (3 linked orders)

    Actions: 'BUY' or 'SELL'

    CAUTION: On a live account, these orders will execute with REAL MONEY.
    This demo uses very small quantities and conservative limits.
    """
    print("\n" + "=" * 70)
    print("SECTION 8: PLACING ORDERS")
    print("=" * 70)

    # --- Market Order ---
    # Executes immediately at the best available price
    print("\n  --- Market Order ---")
    market_order = MarketOrder("BUY", 1)  # Buy 1 share
    print(f"  Created: {market_order}")
    # To actually submit: trade = ib.placeOrder(contract, market_order)

    # --- Limit Order ---
    # Only executes at the specified price or better
    print("\n  --- Limit Order ---")
    limit_order = LimitOrder("BUY", 1, limitPrice=150.00)
    print(f"  Created: {limit_order}")
    # trade = ib.placeOrder(contract, limit_order)

    # --- Stop Order ---
    # Becomes a market order when the stop price is reached
    print("\n  --- Stop Order ---")
    stop_order = StopOrder("SELL", 1, stopPrice=140.00)
    print(f"  Created: {stop_order}")

    # --- Bracket Order ---
    # A bracket order creates 3 linked orders:
    #   1. Entry order (limit buy)
    #   2. Take-profit order (limit sell at higher price)
    #   3. Stop-loss order (stop sell at lower price)
    # When the entry fills, the other two become active (OCA group).
    # When one of the exit orders fills, the other is automatically cancelled.
    print("\n  --- Bracket Order ---")
    bracket = ib.bracketOrder(
        action="BUY",
        quantity=1,
        limitPrice=150.00,     # Entry price
        takeProfitPrice=170.00, # Take profit at $170
        stopLossPrice=140.00,   # Stop loss at $140
    )
    for i, order in enumerate(bracket):
        labels = ["Entry", "Take Profit", "Stop Loss"]
        print(f"    {labels[i]}: {order.orderType} — "
              f"{'Limit: ' + str(order.lmtPrice) if hasattr(order, 'lmtPrice') and order.lmtPrice else ''}"
              f"{'Stop: ' + str(order.auxPrice) if hasattr(order, 'auxPrice') and order.auxPrice else ''}")

    # --- Actually placing an order (commented out for safety) ---
    # Uncomment the lines below to place a real order:
    #
    # trade = ib.placeOrder(contract, limit_order)
    # print(f"  Order placed! Order ID: {trade.order.orderId}")
    # print(f"  Status: {trade.orderStatus.status}")
    #
    # # Wait for the order to be acknowledged
    # ib.sleep(1)
    # print(f"  Updated status: {trade.orderStatus.status}")
    #
    # # The trade object updates in real-time:
    # #   trade.orderStatus.status  — 'PendingSubmit','Submitted','Filled', etc.
    # #   trade.orderStatus.filled  — Number of shares filled
    # #   trade.orderStatus.avgFillPrice — Average fill price
    # #   trade.fills               — List of individual fill details

    print("\n  (Orders are created but NOT submitted — uncomment to place real orders)")


# ============================================================================
# SECTION 9: ORDER MANAGEMENT (Modify & Cancel)
# ============================================================================
def demo_order_management(ib: IB):
    """
    After placing an order, you can:

    - Modify it:  ib.placeOrder(contract, modified_order)
                  (resubmit with same orderId but different parameters)
    - Cancel it:  ib.cancelOrder(order)
    - View all:   ib.openTrades()  — all active/pending orders
                  ib.orders()      — just the Order objects
    """
    print("\n" + "=" * 70)
    print("SECTION 9: ORDER MANAGEMENT")
    print("=" * 70)

    # View all open orders
    open_trades = ib.openTrades()
    print(f"  Open trades: {len(open_trades)}")

    for trade in open_trades:
        print(f"    {trade.contract.symbol} {trade.order.action} "
              f"{trade.order.totalQuantity} @ {trade.order.orderType} "
              f"— Status: {trade.orderStatus.status}")

    # --- Modifying an order ---
    # To modify, re-submit the same order object with changed fields:
    #   trade.order.lmtPrice = 155.00
    #   ib.placeOrder(trade.contract, trade.order)
    #
    # --- Cancelling an order ---
    #   ib.cancelOrder(trade.order)
    #   ib.sleep(1)  # Wait for cancellation confirmation
    #
    # --- Cancel ALL open orders ---
    #   ib.reqGlobalCancel()  # Nuclear option: cancels everything

    print("  (See comments in code for modify/cancel examples)")


# ============================================================================
# SECTION 10: HISTORICAL NEWS & HEADLINES
# ============================================================================
def demo_news(ib: IB, contract):
    """
    News API capabilities:
      - reqNewsProviders()             — List available news sources
      - reqHistoricalNews()            — Headlines for a specific contract
      - reqNewsArticle()               — Full text of a specific article

    Note: News requires appropriate market data subscriptions.
    """
    print("\n" + "=" * 70)
    print("SECTION 10: NEWS")
    print("=" * 70)

    # List available news providers
    providers = ib.reqNewsProviders()
    print(f"  News providers available: {len(providers)}")
    for p in providers:
        print(f"    {p.code}: {p.name}")

    # Request recent headlines for the contract
    # providerCodes — comma-separated list of providers (e.g., 'BZ,FLY')
    if contract.conId and providers:
        headlines = ib.reqHistoricalNews(
            conId=contract.conId,
            providerCodes="+".join(p.code for p in providers[:3]),
            startDateTime="",
            endDateTime="",
            totalResults=5,
        )
        print(f"\n  Recent headlines for {contract.symbol}:")
        for h in headlines:
            print(f"    [{h.time}] {h.headline}")


# ============================================================================
# SECTION 11: OPTION CHAINS
# ============================================================================
def demo_option_chains(ib: IB, stock_contract):
    """
    Option chain retrieval:

    1. reqSecDefOptParams() — Get available expirations and strikes
    2. Create Option contracts for specific strikes/expirations
    3. Request market data or place orders on those options

    This is essential for any options trading strategy.
    """
    print("\n" + "=" * 70)
    print("SECTION 11: OPTION CHAINS")
    print("=" * 70)

    chains = ib.reqSecDefOptParams(
        stock_contract.symbol, "",
        stock_contract.secType, stock_contract.conId
    )

    if chains:
        # Each chain entry represents a different exchange
        chain = chains[0]
        print(f"  Exchange:    {chain.exchange}")
        print(f"  Multiplier:  {chain.multiplier}")

        # Available expirations (sorted, show next 5)
        expirations = sorted(chain.expirations)[:5]
        print(f"  Next 5 Expirations: {expirations}")

        # Available strikes (show a subset around current price)
        strikes = sorted(chain.strikes)
        mid_idx = len(strikes) // 2
        nearby_strikes = strikes[max(0, mid_idx - 3):mid_idx + 3]
        print(f"  Sample Strikes: {nearby_strikes}")

        # Create an option contract for the nearest expiration, nearest strike
        if expirations and nearby_strikes:
            opt = Option(
                stock_contract.symbol,
                expirations[0],         # Nearest expiration
                nearby_strikes[0],      # A nearby strike
                "C",                    # Call
                chain.exchange,
            )
            ib.qualifyContracts(opt)
            print(f"\n  Sample Option Contract: {opt}")
    else:
        print("  No option chain data returned")


# ============================================================================
# SECTION 12: MARKET SCANNERS
# ============================================================================
def demo_scanner(ib: IB):
    """
    Market scanners let you find instruments matching specific criteria,
    similar to the scanner in TWS GUI.

    Popular scan codes:
      - TOP_PERC_GAIN         — Top percentage gainers
      - TOP_PERC_LOSE         — Top percentage losers
      - MOST_ACTIVE           — Highest volume
      - HOT_BY_VOLUME         — Unusual volume
      - HIGH_OPT_IMP_VOLAT    — High implied volatility
      - TOP_OPEN_PERC_GAIN    — Top gainers since open
      - TOP_TRADE_COUNT       — Most trades
      - TOP_PRICE_RANGE       — Largest price range

    You can also get a full list of available scan types:
      ib.reqScannerParameters() → returns XML with all scan types and filters
    """
    print("\n" + "=" * 70)
    print("SECTION 12: MARKET SCANNERS")
    print("=" * 70)

    # Define the scanner criteria
    scanner = ScannerSubscription(
        instrument="STK",              # Stocks
        locationCode="STK.US.MAJOR",   # US major exchanges
        scanCode="TOP_PERC_GAIN",      # Top percentage gainers
        numberOfRows=10,               # Return top 10 results
    )

    # Optional filters
    scanner.abovePrice = 5.0    # Minimum price $5
    scanner.belowPrice = 500.0  # Maximum price $500
    scanner.aboveVolume = 100000  # Minimum volume 100k

    results = ib.reqScannerData(scanner)
    print(f"  Top {len(results)} Gainers (US Stocks, $5-$500, vol > 100k):")
    print(f"  {'Rank':<6} {'Symbol':<8} {'SecType':<8}")
    print(f"  {'-'*6} {'-'*8} {'-'*8}")

    for item in results:
        print(f"  {item.rank:<6} {item.contractDetails.contract.symbol:<8} "
              f"{item.contractDetails.contract.secType:<8}")


# ============================================================================
# SECTION 13: REAL-TIME BARS (5-Second Candles)
# ============================================================================
def demo_realtime_bars(ib: IB, contract):
    """
    reqRealTimeBars() streams live 5-second candles.

    Unlike historical data, these update every 5 seconds with:
      - open, high, low, close of the 5-second period
      - volume and VWAP

    Only 5-second bars are supported (no other intervals).
    The whatToShow parameter can be: TRADES, BID, ASK, or MIDPOINT.

    This is useful for building real-time charts or low-latency strategies.
    """
    print("\n" + "=" * 70)
    print("SECTION 13: REAL-TIME BARS (5-Second)")
    print("=" * 70)

    bars = ib.reqRealTimeBars(contract, barSize=5, whatToShow="TRADES", useRTH=True)

    # The bars list updates automatically. Let's watch for 15 seconds (3 bars).
    print(f"  Streaming 5-second bars for {contract.symbol} (15 seconds)...")

    for i in range(3):
        ib.sleep(5)
        if bars:
            bar = bars[-1]  # Most recent bar
            print(f"    {bar.time} — O:{bar.open:.2f} H:{bar.high:.2f} "
                  f"L:{bar.low:.2f} C:{bar.close:.2f} V:{bar.volume}")

    # Always cancel when done
    ib.cancelRealTimeBars(bars)
    print("  Streaming stopped.")


# ============================================================================
# SECTION 14: PROFIT & LOSS (PnL)
# ============================================================================
def demo_pnl(ib: IB):
    """
    Real-time P&L tracking:

    - reqPnL()         — Total account P&L (daily, unrealized, realized)
    - reqPnLSingle()   — P&L for a specific position (by conId)

    These update in real-time as prices change.
    """
    print("\n" + "=" * 70)
    print("SECTION 14: PROFIT & LOSS")
    print("=" * 70)

    account = ib.managedAccounts()[0]

    # Total account P&L
    pnl = ib.reqPnL(account)
    ib.sleep(1)

    print(f"  Account: {account}")
    print(f"  Daily P&L:      {pnl.dailyPnL}")
    print(f"  Unrealized P&L: {pnl.unrealizedPnL}")
    print(f"  Realized P&L:   {pnl.realizedPnL}")

    ib.cancelPnL(pnl)


# ============================================================================
# SECTION 15: WHAT-IF ORDERS (Order Preview)
# ============================================================================
def demo_whatif_order(ib: IB, contract):
    """
    "What-If" orders let you preview the impact of an order WITHOUT placing it.

    Returns:
      - Estimated commission
      - Margin impact (initial and maintenance)
      - Estimated max commission
      - Equity with loan value

    This is invaluable for checking margin requirements before placing orders.
    """
    print("\n" + "=" * 70)
    print("SECTION 15: WHAT-IF ORDER (Preview)")
    print("=" * 70)

    order = MarketOrder("BUY", 100)  # Preview buying 100 shares

    # whatIfOrder=True returns the projected impact without actually submitting
    trade = ib.placeOrder(contract, order)
    ib.sleep(1)

    # NOTE: what-if is done by setting order.whatIf = True
    # Here's the proper way:
    order_preview = MarketOrder("BUY", 100)
    order_preview.whatIf = True
    preview_trade = ib.placeOrder(contract, order_preview)
    ib.sleep(1)

    status = preview_trade.orderStatus
    print(f"  What-If: BUY 100 {contract.symbol}")
    print(f"  Commission:       {status.commission}")
    print(f"  Init Margin:      {status.initMarginChange}")
    print(f"  Maint Margin:     {status.maintMarginChange}")
    print(f"  Equity w/ Loan:   {status.equityWithLoanChange}")

    # Cancel the what-if (it's not a real order, but clean up)
    ib.cancelOrder(trade.order)


# ============================================================================
# SECTION 16: EVENT CALLBACKS
# ============================================================================
def demo_events(ib: IB, contract):
    """
    The IB API is event-driven. You can register callbacks for:

      ib.pendingTickersEvent  — When tickers have new data
      ib.orderStatusEvent     — When an order status changes
      ib.newOrderEvent        — When a new order is detected
      ib.execDetailsEvent     — When an order gets filled (execution)
      ib.errorEvent           — When IB sends an error/warning
      ib.connectedEvent       — When connection is established
      ib.disconnectedEvent    — When connection is lost
      ib.barUpdateEvent       — When real-time bars update
      ib.positionEvent        — When positions change
      ib.accountValueEvent    — When account values change

    This is useful for building reactive, real-time trading systems.
    """
    print("\n" + "=" * 70)
    print("SECTION 16: EVENT CALLBACKS")
    print("=" * 70)

    # Define callback functions
    def on_pending_tickers(tickers):
        """Called whenever any subscribed ticker gets new data."""
        for t in tickers:
            print(f"    [Tick] {t.contract.symbol}: "
                  f"bid={t.bid}, ask={t.ask}, last={t.last}")

    def on_error(reqId, errorCode, errorString, contract):
        """Called when IB sends an error or warning message."""
        print(f"    [Error] reqId={reqId}, code={errorCode}: {errorString}")

    # Register callbacks
    ib.pendingTickersEvent += on_pending_tickers
    ib.errorEvent += on_error

    # Subscribe to market data to trigger the ticker callback
    ib.reqMarketDataType(3)  # Delayed
    ticker = ib.reqMktData(contract)

    print(f"  Listening for events on {contract.symbol} for 5 seconds...")
    ib.sleep(5)

    # Clean up: remove callbacks and cancel data
    ib.pendingTickersEvent -= on_pending_tickers
    ib.errorEvent -= on_error
    ib.cancelMktData(contract)

    print("  Event listeners removed.")


# ============================================================================
# MAIN — Run all demos
# ============================================================================
def main():
    """
    Main entry point. Connects to TWS and runs each demo section.

    Toggle sections on/off by commenting out the function calls below.
    """
    print("=" * 70)
    print("  INTERACTIVE BROKERS TWS API DEMO")
    print("  Using: ib_insync (Python)")
    print("=" * 70)

    # Create the IB instance (the main API client)
    ib = IB()

    try:
        # SECTION 1: Connect to TWS
        demo_connection(ib)

        # SECTION 2: Define contracts (no connection needed)
        apple, eurusd, es_future, aapl_call = demo_contracts()

        # Qualify AAPL so we can use it in subsequent demos
        ib.qualifyContracts(apple)

        # SECTION 3: Contract details & search
        demo_contract_details(ib, apple)

        # SECTION 4: Live streaming market data
        demo_live_market_data(ib, apple)

        # SECTION 5: Snapshot (one-time) quote
        demo_snapshot(ib, eurusd)

        # SECTION 6: Historical data (OHLCV bars)
        demo_historical_data(ib, apple)

        # SECTION 7: Account information & portfolio
        demo_account_portfolio(ib)

        # SECTION 8: Order types (created but NOT submitted)
        demo_orders(ib, apple)

        # SECTION 9: Order management
        demo_order_management(ib)

        # SECTION 10: News
        demo_news(ib, apple)

        # SECTION 11: Option chains
        demo_option_chains(ib, apple)

        # SECTION 12: Market scanner
        demo_scanner(ib)

        # SECTION 13: Real-time 5-second bars
        demo_realtime_bars(ib, apple)

        # SECTION 14: P&L tracking
        demo_pnl(ib)

        # SECTION 15: What-if order preview
        # NOTE: Uncomment carefully — this places a what-if order
        # demo_whatif_order(ib, apple)

        # SECTION 16: Event-driven callbacks
        demo_events(ib, apple)

    except Exception as e:
        print(f"\nERROR: {e}")
        print("Make sure TWS/IB Gateway is running and API is enabled.")
        print("  TWS: Edit → Global Configuration → API → Settings")
        print(f"  Expected port: {TWS_PORT}")

    finally:
        # Always disconnect cleanly
        if ib.isConnected():
            ib.disconnect()
            print("\nDisconnected from TWS.")

    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
