"""
===============================================================================
 Interactive Brokers TWS API — Uncovered APIs Demo (Third Demo)
===============================================================================

This third demo targets useful APIs that are not covered by the first two demos.
It focuses on reference-data, microstructure, reporting, and diagnostic workflows:

  1) Market depth exchanges + market rules
  2) Smart routing components (when available)
  3) Fundamental XML reports
  4) Head timestamp + histogram data
  5) News article body retrieval (not just headlines)
  6) Execution/completed-order reporting
  7) Per-position PnL stream (reqPnLSingle)
  8) Proper what-if preview (whatIfOrder)

Usage:
  python tws_api_uncovered_demo.py
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ib_insync import ExecutionFilter, IB, MarketOrder, Stock, util


TWS_HOST = "127.0.0.1"
TWS_PORT = 7497
CLIENT_ID = 11


@dataclass
class DemoConfig:
    symbol: str = "AAPL"
    use_delayed_data: bool = True


def banner(title: str) -> None:
    print("\n" + "=" * 86)
    print(title)
    print("=" * 86)


def run_section(title: str, fn: Callable[[], None]) -> None:
    banner(title)
    try:
        fn()
    except Exception as exc:
        print(f"Skipped due to API/entitlement limitation: {exc}")


def connect_ib() -> IB:
    banner("0) CONNECT")
    ib = IB()
    ib.connect(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)
    print(f"Connected: {ib.isConnected()}")
    print(f"Server time: {ib.reqCurrentTime()}")
    print(f"Managed accounts: {ib.managedAccounts()}")
    return ib


def demo_market_structure(ib: IB, contract: Stock) -> None:
    def _inner() -> None:
        details = ib.reqContractDetails(contract)
        if not details:
            print("No contract details returned.")
            return

        detail = details[0]
        print(f"Long name: {detail.longName}")
        print(f"Valid exchanges: {detail.validExchanges}")
        print(f"Market rule ids: {detail.marketRuleIds}")

        exchange_rows = ib.reqMktDepthExchanges()
        print(f"Depth exchange definitions: {len(exchange_rows)}")
        for row in exchange_rows[:5]:
            print(f"  {row.exchange} {row.secType} -> {row.listingExch}")

        market_rule_ids = [x for x in detail.marketRuleIds.split(",") if x]
        if market_rule_ids:
            first_rule_id = int(market_rule_ids[0])
            increments = ib.reqMarketRule(first_rule_id)
            print(f"Price increments for marketRuleId={first_rule_id} (sample):")
            for inc in increments[:5]:
                print(f"  lowEdge={inc.lowEdge} increment={inc.increment}")

        valid_exchanges = [x for x in detail.validExchanges.split(",") if x]
        if valid_exchanges:
            smart_components = ib.reqSmartComponents(valid_exchanges[0])
            print(f"Smart components for {valid_exchanges[0]}: {len(smart_components)}")
            for bit, comp in list(smart_components.items())[:5]:
                print(f"  bit={bit} exchange={comp.exchange} letter={comp.exchangeLetter}")

    run_section("1) MARKET STRUCTURE APIS", _inner)


def demo_fundamental_and_reference(ib: IB, contract: Stock) -> None:
    def _inner() -> None:
        snapshot_xml = ib.reqFundamentalData(contract, reportType="ReportSnapshot")
        if snapshot_xml:
            print("ReportSnapshot XML returned (first 240 chars):")
            print(snapshot_xml[:240].replace("\n", " "))
        else:
            print("No fundamental snapshot data returned.")

        head_ts = ib.reqHeadTimeStamp(
            contract=contract,
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1,
        )
        print(f"Head timestamp (earliest available TRADES data): {head_ts}")

        histogram = ib.reqHistogramData(contract, useRTH=True, period="20 days")
        print(f"Histogram buckets: {len(histogram)}")
        for bucket in histogram[:5]:
            print(f"  price={bucket.price} size={bucket.count}")

    run_section("2) FUNDAMENTAL + REFERENCE APIS", _inner)


def demo_news_article_body(ib: IB, contract: Stock) -> None:
    def _inner() -> None:
        providers = ib.reqNewsProviders()
        if not providers:
            print("No entitled news providers.")
            return

        provider_codes = "+".join(p.code for p in providers[:2])
        headlines = ib.reqHistoricalNews(
            conId=contract.conId,
            providerCodes=provider_codes,
            startDateTime="",
            endDateTime="",
            totalResults=3,
        )
        print(f"Headlines returned: {len(headlines)}")
        if not headlines:
            return

        first = headlines[0]
        print(f"First headline: [{first.providerCode}] {first.headline}")
        article = ib.reqNewsArticle(first.providerCode, first.articleId)
        article_len = len(article.articleText) if article and article.articleText else 0
        print(f"Article type={article.articleType} body_length={article_len}")
        if article_len:
            print(f"Article preview: {article.articleText[:240].replace(chr(10), ' ')}")

    run_section("3) NEWS ARTICLE BODY API", _inner)


def demo_reporting_apis(ib: IB) -> None:
    def _inner() -> None:
        executions = ib.reqExecutions(ExecutionFilter())
        print(f"Executions returned: {len(executions)}")
        for fill in executions[:5]:
            ex = fill.execution
            print(
                f"  time={ex.time} side={ex.side} shares={ex.shares} "
                f"symbol={fill.contract.symbol} price={ex.price}"
            )

        completed_orders = ib.reqCompletedOrders(apiOnly=False)
        print(f"Completed orders returned: {len(completed_orders)}")
        for trade in completed_orders[:5]:
            print(
                f"  id={trade.order.orderId} type={trade.order.orderType} "
                f"status={trade.orderStatus.status} symbol={trade.contract.symbol}"
            )

    run_section("4) EXECUTION + COMPLETED ORDER REPORTS", _inner)


def demo_single_position_pnl(ib: IB) -> None:
    def _inner() -> None:
        accounts = ib.managedAccounts()
        positions = ib.positions()
        if not accounts or not positions:
            print("No account/position available for reqPnLSingle.")
            return

        account = accounts[0]
        first_position = positions[0]
        pnl_single = ib.reqPnLSingle(account, "", first_position.contract.conId)
        ib.sleep(2)
        print(
            f"PnLSingle for {first_position.contract.symbol} conId={first_position.contract.conId} -> "
            f"daily={pnl_single.dailyPnL} unrealized={pnl_single.unrealizedPnL} realized={pnl_single.realizedPnL}"
        )
        ib.cancelPnLSingle(pnl_single)

    run_section("5) PER-POSITION PNL STREAM", _inner)


def demo_whatif_preview(ib: IB, contract: Stock) -> None:
    def _inner() -> None:
        preview_order = MarketOrder("BUY", 10)
        order_state = ib.whatIfOrder(contract, preview_order)
        print("whatIfOrder returned projected impact:")
        print(f"  initMarginChange={order_state.initMarginChange}")
        print(f"  maintMarginChange={order_state.maintMarginChange}")
        print(f"  equityWithLoanChange={order_state.equityWithLoanChange}")
        print(f"  commission={order_state.commission} maxCommission={order_state.maxCommission}")

    run_section("6) WHAT-IF ORDER PREVIEW API", _inner)


def main() -> None:
    util.startLoop()
    cfg = DemoConfig()
    ib = connect_ib()

    try:
        if cfg.use_delayed_data:
            ib.reqMarketDataType(3)

        contract = Stock(cfg.symbol, "SMART", "USD")
        ib.qualifyContracts(contract)

        demo_market_structure(ib, contract)
        demo_fundamental_and_reference(ib, contract)
        demo_news_article_body(ib, contract)
        demo_reporting_apis(ib)
        demo_single_position_pnl(ib)
        demo_whatif_preview(ib, contract)
    finally:
        banner("DONE: DISCONNECT")
        ib.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
