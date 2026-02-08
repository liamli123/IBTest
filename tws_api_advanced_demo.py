"""
===============================================================================
 Interactive Brokers TWS API — Advanced Demo
===============================================================================

This advanced demo builds on the basic demo and focuses on more complex API
workflows that are common in real trading/research systems:

  1) Event-driven market data stream handling
  2) Historical + real-time bar stitching
  3) Option chain discovery + contract selection
  4) Multi-leg combo contract construction
  5) Bracket + OCA order workflows
  6) Scanner + symbol resolution pipeline
  7) News provider + contract headlines retrieval

PREREQUISITES:
  - TWS or IB Gateway running
  - API enabled in TWS
  - Prefer PAPER account (7497)

Usage:
  python tws_api_advanced_demo.py
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from ib_insync import (
    IB,
    Stock,
    Option,
    ComboLeg,
    Contract,
    ContractDetails,
    LimitOrder,
    ScannerSubscription,
    Ticker,
    util,
)


TWS_HOST = "127.0.0.1"
TWS_PORT = 7497
CLIENT_ID = 7


@dataclass
class DemoConfig:
    use_delayed_data: bool = True
    stock_symbol: str = "AAPL"
    option_symbol: str = "AAPL"
    option_exchange: str = "SMART"
    option_right: str = "C"
    target_strike_near_money: bool = True
    combo_symbol: str = "MSFT"


def banner(title: str) -> None:
    print("\n" + "=" * 84)
    print(title)
    print("=" * 84)


def connect_ib() -> IB:
    banner("1) CONNECTION + SESSION STATE")
    ib = IB()
    ib.connect(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)
    print(f"Connected: {ib.isConnected()}")
    print(f"Server time: {ib.reqCurrentTime()}")
    print(f"Managed accounts: {ib.managedAccounts()}")
    return ib


def setup_market_data_mode(ib: IB, use_delayed_data: bool) -> None:
    mode = 3 if use_delayed_data else 1
    ib.reqMarketDataType(mode)
    print(f"Market data mode: {'Delayed' if mode == 3 else 'Live'} ({mode})")


def demo_event_driven_market_data(ib: IB, symbol: str) -> None:
    banner("2) EVENT-DRIVEN STREAMING MARKET DATA")
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    ticker = ib.reqMktData(contract, genericTickList="233,236", snapshot=False)

    def on_pending_tickers(tickers: List[Ticker]) -> None:
        for tick in tickers:
            if tick.contract.conId == contract.conId:
                print(
                    f"tick {datetime.now().strftime('%H:%M:%S')} "
                    f"bid={tick.bid} ask={tick.ask} last={tick.last} vol={tick.volume}"
                )

    ib.pendingTickersEvent += on_pending_tickers
    print("Listening for market data events for ~6 seconds...")
    ib.sleep(6)
    ib.pendingTickersEvent -= on_pending_tickers
    ib.cancelMktData(contract)


def demo_hist_plus_realtime(ib: IB, symbol: str) -> None:
    banner("3) HISTORICAL + REAL-TIME BAR PIPELINE")
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="2 D",
        barSizeSetting="5 mins",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
        keepUpToDate=False,
    )
    print(f"Historical bars fetched: {len(bars)}")
    if bars:
        print(f"Last hist bar: {bars[-1].date} O={bars[-1].open} H={bars[-1].high} L={bars[-1].low} C={bars[-1].close}")

    rt_bars = ib.reqRealTimeBars(contract, barSize=5, whatToShow="TRADES", useRTH=False)

    def on_rt_update(bar_list, has_new_bar: bool) -> None:
        if has_new_bar and len(bar_list) > 0:
            b = bar_list[-1]
            print(f"rtbar {b.time} O={b.open_} H={b.high} L={b.low} C={b.close} V={b.volume}")

    rt_bars.updateEvent += on_rt_update
    print("Collecting real-time bars for ~12 seconds...")
    ib.sleep(12)
    rt_bars.updateEvent -= on_rt_update
    ib.cancelRealTimeBars(rt_bars)


def pick_option_contract(
    ib: IB,
    underlying: Stock,
    right: str,
    target_strike_near_money: bool,
) -> Optional[Option]:
    chain_params = ib.reqSecDefOptParams(
        underlying.symbol,
        "",
        underlying.secType,
        underlying.conId,
    )
    if not chain_params:
        return None

    chain = next((c for c in chain_params if c.exchange in {"SMART", "CBOE"}), chain_params[0])
    expirations = sorted(chain.expirations)
    strikes = sorted(s for s in chain.strikes if s > 0)
    if not expirations or not strikes:
        return None

    expiry = expirations[0]

    strike = strikes[len(strikes) // 2]
    if target_strike_near_money:
        tk = ib.reqMktData(underlying, snapshot=True)
        ib.sleep(2)
        ref_price = tk.last or tk.close or tk.marketPrice()
        if ref_price:
            strike = min(strikes, key=lambda s: abs(s - ref_price))

    option = Option(underlying.symbol, expiry, strike, right, chain.exchange)
    ib.qualifyContracts(option)
    return option


def demo_option_chain_and_combo(ib: IB, symbol: str, right: str, near_money: bool) -> None:
    banner("4) OPTION CHAIN DISCOVERY + COMBO CONSTRUCTION")

    underlying = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(underlying)

    selected = pick_option_contract(ib, underlying, right, near_money)
    if not selected:
        print("Unable to derive option contract from chain.")
        return

    print(
        "Selected option: "
        f"{selected.symbol} {selected.lastTradeDateOrContractMonth} "
        f"{selected.strike}{selected.right} @ {selected.exchange} conId={selected.conId}"
    )

    chain_details: List[ContractDetails] = ib.reqContractDetails(selected)
    if chain_details:
        cd = chain_details[0]
        print(f"Multiplier={cd.contract.multiplier} TradingClass={cd.contract.tradingClass} MinTick={cd.minTick}")

    offset_strike = selected.strike + 5
    second_leg = Option(
        selected.symbol,
        selected.lastTradeDateOrContractMonth,
        offset_strike,
        selected.right,
        selected.exchange,
    )
    detail2 = ib.reqContractDetails(second_leg)
    if not detail2:
        print("Could not resolve second option leg for combo; skipping combo demo.")
        return
    second_leg = detail2[0].contract

    combo = Contract(
        symbol=selected.symbol,
        secType="BAG",
        currency="USD",
        exchange="SMART",
        comboLegs=[
            ComboLeg(conId=selected.conId, ratio=1, action="BUY", exchange=selected.exchange),
            ComboLeg(conId=second_leg.conId, ratio=1, action="SELL", exchange=second_leg.exchange),
        ],
    )
    print("Constructed vertical spread combo contract (BAG) with legs:")
    for leg in combo.comboLegs:
        print(f"  conId={leg.conId} ratio={leg.ratio} action={leg.action} ex={leg.exchange}")


def demo_orders_bracket_and_oca(ib: IB, symbol: str) -> None:
    banner("5) ADVANCED ORDER STRUCTURES (BRACKET + OCA)")
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    md = ib.reqMktData(contract, snapshot=True)
    ib.sleep(2)
    px = md.last or md.close or 100.0

    parent_lmt = round(px * 0.995, 2)
    take_profit = round(px * 1.01, 2)
    stop_loss = round(px * 0.985, 2)

    bracket = ib.bracketOrder(
        action="BUY",
        quantity=1,
        limitPrice=parent_lmt,
        takeProfitPrice=take_profit,
        stopLossPrice=stop_loss,
    )

    print("Prepared bracket orders (not transmitted by default in this demo):")
    for idx, order in enumerate(bracket, 1):
        order.transmit = False
        print(f"  Leg {idx}: type={order.orderType} action={order.action} qty={order.totalQuantity} transmit={order.transmit}")

    oca_group = f"OCA_{int(datetime.now().timestamp())}"
    buy1 = LimitOrder("BUY", 1, round(px * 0.99, 2))
    buy2 = LimitOrder("BUY", 1, round(px * 0.985, 2))
    for order in (buy1, buy2):
        order.ocaGroup = oca_group
        order.ocaType = 1
        order.transmit = False

    print(f"Prepared OCA pair with group={oca_group} (first fill cancels peer):")
    print(f"  OCA order A limit={buy1.lmtPrice}")
    print(f"  OCA order B limit={buy2.lmtPrice}")

    # Example placement calls intentionally commented for safety:
    # trade_parent = ib.placeOrder(contract, bracket[0])
    # trade_tp = ib.placeOrder(contract, bracket[1])
    # trade_sl = ib.placeOrder(contract, bracket[2])
    # trade_oca_a = ib.placeOrder(contract, buy1)
    # trade_oca_b = ib.placeOrder(contract, buy2)


def demo_scanner_to_contracts(ib: IB) -> None:
    banner("6) SCANNER PIPELINE -> RESOLVED CONTRACTS")

    scan = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        numberOfRows=5,
    )
    results = ib.reqScannerData(scan)
    print(f"Scanner rows: {len(results)}")

    for row in results:
        c = row.contractDetails.contract
        print(f"  rank={row.rank} symbol={c.symbol} primary={c.primaryExchange} currency={c.currency}")

    if results:
        first = results[0].contractDetails.contract
        matches = ib.reqMatchingSymbols(first.symbol)
        print(f"Symbol resolution candidates for {first.symbol}: {len(matches)}")
        for m in matches[:3]:
            print(f"  {m.contract.symbol} {m.contract.secType} @ {m.contract.primaryExchange}")


def demo_news_pipeline(ib: IB, symbol: str) -> None:
    banner("7) NEWS PROVIDERS + CONTRACT HEADLINES")
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)

    providers = ib.reqNewsProviders()
    print(f"News providers available: {len(providers)}")
    if providers:
        print("  Provider codes:", ", ".join(p.code for p in providers[:5]))

    provider_codes = "+".join(p.code for p in providers[:2]) if providers else ""
    if not provider_codes:
        print("No provider entitlements available; skipping headlines request.")
        return

    headlines = ib.reqHistoricalNews(
        conId=contract.conId,
        providerCodes=provider_codes,
        startDateTime="",
        endDateTime="",
        totalResults=5,
    )
    print(f"Headlines fetched: {len(headlines)}")
    for h in headlines:
        print(f"  {h.time} | {h.providerCode} | {h.headline[:120]}")


def main() -> None:
    util.startLoop()  # Safe no-op in normal script mode, useful in notebooks.
    config = DemoConfig()
    ib = connect_ib()

    try:
        setup_market_data_mode(ib, config.use_delayed_data)
        demo_event_driven_market_data(ib, config.stock_symbol)
        demo_hist_plus_realtime(ib, config.stock_symbol)
        demo_option_chain_and_combo(
            ib,
            config.option_symbol,
            config.option_right,
            config.target_strike_near_money,
        )
        demo_orders_bracket_and_oca(ib, config.stock_symbol)
        demo_scanner_to_contracts(ib)
        demo_news_pipeline(ib, config.stock_symbol)
    finally:
        banner("DONE: DISCONNECT")
        ib.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
