"""
===============================================================================
 Buffett + Munger Value Investing Dashboard (IB API)
===============================================================================

Single ticker -> detailed dashboard with:
  - Fundamental quality/strength scoring
  - Multi-model intrinsic value estimate
  - News sentiment + narrative risk scan
  - Buffett/Munger mental-model checklist
  - Recommendation with margin-of-safety discipline

Usage:
  python buffett_munger_dashboard.py --ticker AAPL
===============================================================================
"""

from __future__ import annotations

import argparse
import math
import re
import statistics
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ib_insync import IB, Stock, util


TWS_HOST = "127.0.0.1"
TWS_PORT = 7497
CLIENT_ID = 31


POSITIVE_WORDS = {
    "beat", "beats", "growth", "strong", "record", "upside", "surge", "profit",
    "profits", "improve", "improves", "improved", "expands", "expansion",
    "outperform", "outperformed", "bullish", "upgrade", "momentum", "resilient",
    "advantage", "leadership", "discipline", "cashflow", "buyback",
}
NEGATIVE_WORDS = {
    "miss", "misses", "weak", "drop", "plunge", "decline", "declines", "downside",
    "warning", "warns", "loss", "losses", "lawsuit", "downgrade", "bearish",
    "investigation", "cut", "cuts", "slump", "recession", "fraud", "restatement",
    "bankruptcy", "dilution", "liquidity",
}

RED_FLAG_WORDS = {
    "fraud", "investigation", "restatement", "bankruptcy", "default",
    "insolvency", "probe", "subpoena", "whistleblower", "accounting",
}


@dataclass
class Inputs:
    ticker: str
    use_delayed_data: bool = True
    news_items: int = 18


@dataclass
class Snapshot:
    metrics: Dict[str, float]

    def get_any(self, keys: Sequence[str]) -> Optional[float]:
        lowered = {name.lower(): value for name, value in self.metrics.items()}
        for key in keys:
            if key.lower() in lowered:
                return lowered[key.lower()]
        return None


@dataclass
class DashboardData:
    price: float
    metrics: Dict[str, Optional[float]]
    history_growth: Optional[float]
    drawdown: Optional[float]
    volatility: Optional[float]
    positive_month_ratio: Optional[float]
    sentiment: float
    sentiment_coverage: int
    red_flags: int
    moat_score: float
    quality_score: float
    predictability_score: float
    management_score: float
    risk_score: float
    intrinsic_value: Optional[float]
    margin_of_safety: Optional[float]
    recommendation: str
    model_breakdown: Dict[str, float]


def banner(title: str) -> None:
    print("\n" + "=" * 96)
    print(title)
    print("=" * 96)


def safe_float(value: Optional[object]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    text = str(value).strip().replace(",", "")
    if not text or text.upper() in {"N/A", "NA", "NONE", "NULL", "-"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def pct(value: Optional[float]) -> Optional[float]:
    number = safe_float(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 1 else number


def parse_snapshot(xml_text: str) -> Snapshot:
    metrics: Dict[str, float] = {}
    if not xml_text:
        return Snapshot(metrics=metrics)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return Snapshot(metrics=metrics)

    name_keys = ("FieldName", "fieldName", "Name", "name", "Tag", "tag")
    value_keys = ("Value", "value", "v")

    for element in root.iter():
        metric_name = None
        for attr in name_keys:
            item = element.attrib.get(attr)
            if item:
                metric_name = item.strip()
                break
        if not metric_name:
            continue

        raw_value = None
        for attr in value_keys:
            if attr in element.attrib:
                raw_value = element.attrib[attr]
                break
        if raw_value is None:
            raw_value = (element.text or "").strip()

        num = safe_float(raw_value)
        if num is not None:
            metrics[metric_name] = num
    return Snapshot(metrics=metrics)


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def clamp(number: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, number))


def to_score(number: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    scaled = (number - low) / (high - low)
    return clamp((scaled * 2.0) - 1.0, -1.0, 1.0)


def get_price(ib: IB, contract: Stock) -> float:
    ticker = ib.reqMktData(contract, snapshot=True)
    ib.sleep(2)
    for field in (ticker.last, ticker.close, ticker.marketPrice(), ticker.bid, ticker.ask):
        value = safe_float(field)
        if value and value > 0:
            return value
    raise RuntimeError("Could not retrieve price.")


def get_history_stats(
    ib: IB,
    contract: Stock,
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    bars = ib.reqHistoricalData(
        contract=contract,
        endDateTime="",
        durationStr="10 Y",
        barSizeSetting="1 month",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    prices = [safe_float(bar.close) for bar in bars]
    prices = [value for value in prices if value and value > 0]
    if len(prices) < 24:
        return None, None, None, None

    start = prices[0]
    end = prices[-1]
    years = len(prices) / 12.0
    cagr = (end / start) ** (1 / years) - 1 if start > 0 else None

    peak = prices[0]
    max_drawdown = 0.0
    for price in prices:
        peak = max(peak, price)
        if peak > 0:
            max_drawdown = min(max_drawdown, (price - peak) / peak)

    returns: List[float] = []
    positive = 0
    for i in range(1, len(prices)):
        prev_price = prices[i - 1]
        if prev_price <= 0:
            continue
        ret = prices[i] / prev_price - 1
        returns.append(ret)
        if ret > 0:
            positive += 1

    volatility = statistics.pstdev(returns) if returns else None
    positive_ratio = (positive / len(returns)) if returns else None
    return cagr, max_drawdown, volatility, positive_ratio


def get_sentiment(ib: IB, con_id: int, total_results: int) -> Tuple[float, int, int]:
    providers = ib.reqNewsProviders()
    if not providers:
        return 0.0, 0, 0

    provider_codes = "+".join(p.code for p in providers[:3])
    headlines = ib.reqHistoricalNews(
        conId=con_id,
        providerCodes=provider_codes,
        startDateTime="",
        endDateTime="",
        totalResults=total_results,
    )
    if not headlines:
        return 0.0, 0, 0

    sentiment_acc = 0.0
    scored = 0
    red_flags = 0

    for headline in headlines:
        text_items = [headline.headline or ""]
        try:
            article = ib.reqNewsArticle(headline.providerCode, headline.articleId)
            if article and article.articleText:
                text_items.append(article.articleText[:1200])
        except Exception:
            pass

        words: List[str] = []
        for item in text_items:
            words.extend(tokenize(item))
        if not words:
            continue

        positive = sum(1 for word in words if word in POSITIVE_WORDS)
        negative = sum(1 for word in words if word in NEGATIVE_WORDS)
        if positive + negative > 0:
            sentiment_acc += (positive - negative) / (positive + negative)
            scored += 1
        red_flags += sum(1 for word in words if word in RED_FLAG_WORDS)

    if scored == 0:
        return 0.0, 0, red_flags
    return clamp(sentiment_acc / scored, -1.0, 1.0), scored, red_flags


def extract_metrics(snapshot: Snapshot) -> Dict[str, Optional[float]]:
    return {
        "eps": snapshot.get_any(("EPS", "EPS_TTM", "TTMEPSXCLX", "DilutedEPSExclExtraTTM")),
        "bvps": snapshot.get_any(("BookValuePerShare", "BVPS", "QBVPS")),
        "pe": snapshot.get_any(("PERatio", "PE", "TTMPR2EPS")),
        "pb": snapshot.get_any(("Price2Book", "PriceToBook", "PB")),
        "roe": pct(snapshot.get_any(("ROE", "ReturnOnEquity", "TTMROEPCT"))),
        "roic": pct(snapshot.get_any(("ROIC", "ReturnOnInvestedCapital"))),
        "gross_margin": pct(snapshot.get_any(("GrossMargin", "TTMGROSMGN"))),
        "oper_margin": pct(snapshot.get_any(("OperatingMargin", "TTMOPMGN"))),
        "net_margin": pct(snapshot.get_any(("NetProfitMargin", "TTMNPMGN"))),
        "debt_to_equity": snapshot.get_any(("DebtToEquity", "TotalDebtToEquity", "LTDebt2Equity")),
        "current_ratio": snapshot.get_any(("CurrentRatio",)),
        "interest_cover": snapshot.get_any(("InterestCoverage",)),
        "dividend_yield": pct(snapshot.get_any(("DividendYield", "DivYield"))),
    }


def score_moat(metrics: Dict[str, Optional[float]]) -> float:
    score = 0.0
    if metrics["gross_margin"] is not None:
        score += to_score(metrics["gross_margin"], 0.20, 0.60) * 0.30
    if metrics["oper_margin"] is not None:
        score += to_score(metrics["oper_margin"], 0.07, 0.30) * 0.35
    if metrics["roe"] is not None:
        score += to_score(metrics["roe"], 0.08, 0.25) * 0.35
    return clamp(score, -1.0, 1.0)


def score_quality(metrics: Dict[str, Optional[float]]) -> float:
    score = 0.0
    if metrics["roe"] is not None:
        score += to_score(metrics["roe"], 0.08, 0.22) * 0.30
    if metrics["roic"] is not None:
        score += to_score(metrics["roic"], 0.07, 0.20) * 0.30
    if metrics["debt_to_equity"] is not None:
        score += to_score(1.5 - metrics["debt_to_equity"], 0.0, 1.3) * 0.20
    if metrics["current_ratio"] is not None:
        score += to_score(metrics["current_ratio"], 1.0, 2.2) * 0.10
    if metrics["interest_cover"] is not None:
        score += to_score(metrics["interest_cover"], 2.0, 10.0) * 0.10
    return clamp(score, -1.0, 1.0)


def score_predictability(
    growth: Optional[float],
    drawdown: Optional[float],
    volatility: Optional[float],
    positive_ratio: Optional[float],
) -> float:
    score = 0.0
    if growth is not None:
        score += to_score(growth, 0.02, 0.15) * 0.35
    if drawdown is not None:
        score += to_score(-drawdown, 0.15, 0.55) * 0.25
    if volatility is not None:
        score += to_score(0.20 - volatility, -0.05, 0.16) * 0.20
    if positive_ratio is not None:
        score += to_score(positive_ratio, 0.45, 0.70) * 0.20
    return clamp(score, -1.0, 1.0)


def score_management(metrics: Dict[str, Optional[float]], sentiment: float) -> float:
    score = 0.0
    if metrics["roic"] is not None:
        score += to_score(metrics["roic"], 0.07, 0.18) * 0.40
    if metrics["dividend_yield"] is not None:
        score += to_score(metrics["dividend_yield"], 0.0, 0.04) * 0.10
    if metrics["debt_to_equity"] is not None:
        score += to_score(1.2 - metrics["debt_to_equity"], 0.0, 1.0) * 0.25
    score += sentiment * 0.25
    return clamp(score, -1.0, 1.0)


def score_risk(red_flags: int, debt_to_equity: Optional[float], drawdown: Optional[float]) -> float:
    score = 0.0
    if red_flags > 0:
        score -= clamp(red_flags / 30.0, 0.0, 0.4)
    if debt_to_equity is not None:
        score += to_score(1.4 - debt_to_equity, -0.8, 1.2) * 0.35
    if drawdown is not None:
        score += to_score(-drawdown, 0.10, 0.55) * 0.25
    return clamp(score, -1.0, 1.0)


def intrinsic_value_estimate(
    price: float,
    metrics: Dict[str, Optional[float]],
    growth: Optional[float],
    moat_score: float,
    sentiment: float,
) -> Tuple[Optional[float], Dict[str, float], Optional[float]]:
    eps = metrics["eps"]
    bvps = metrics["bvps"]
    growth_rate = clamp(growth if growth is not None else 0.05, -0.01, 0.18)
    growth_pct = growth_rate * 100.0

    models: Dict[str, float] = {}
    if eps and eps > 0:
        graham = eps * (8.5 + (2 * growth_pct))
        models["graham"] = graham

        fair_pe = 11.0 + 8.0 * clamp(moat_score, -0.5, 1.0) + 3.0 * clamp(sentiment, -0.25, 0.25)
        fair_pe = clamp(fair_pe, 8.0, 28.0)
        models["earnings_power"] = eps * fair_pe

        owner_earnings_growth = clamp(growth_rate, 0.00, 0.12)
        discount_rate = 0.10
        terminal_multiple = 12.0
        oe = eps
        pv = 0.0
        for year in range(1, 6):
            oe *= (1.0 + owner_earnings_growth)
            pv += oe / ((1.0 + discount_rate) ** year)
        terminal = (oe * terminal_multiple) / ((1.0 + discount_rate) ** 5)
        models["owner_earnings"] = pv + terminal

    if bvps and bvps > 0:
        fair_pb = clamp(1.2 + (0.9 * moat_score), 0.6, 3.2)
        models["book_anchor"] = bvps * fair_pb

    if not models:
        return None, {}, None

    weights = {
        "graham": 0.25,
        "earnings_power": 0.25,
        "owner_earnings": 0.35,
        "book_anchor": 0.15,
    }
    present = {name: weights[name] for name in models}
    total_w = sum(present.values())
    intrinsic = sum(models[name] * present[name] for name in models) / total_w
    margin = ((intrinsic - price) / price) if price > 0 else None
    return intrinsic, models, margin


def recommendation(
    margin: Optional[float],
    moat: float,
    quality: float,
    predictability: float,
    management: float,
    risk: float,
    sentiment: float,
) -> str:
    if margin is None:
        return "INSUFFICIENT DATA"
    total = (
        (margin * 0.45) +
        (moat * 0.12) +
        (quality * 0.15) +
        (predictability * 0.12) +
        (management * 0.08) +
        (risk * 0.05) +
        (sentiment * 0.03)
    )
    if total >= 0.28:
        return "STRONG BUY"
    if total >= 0.12:
        return "BUY"
    if total > -0.04:
        return "HOLD"
    if total > -0.15:
        return "REDUCE"
    return "SELL"


def collect_dashboard_data(ib: IB, ticker: str, news_items: int) -> DashboardData:
    contract = Stock(ticker, "SMART", "USD")
    ib.qualifyContracts(contract)
    price = get_price(ib, contract)

    snapshot_xml = ib.reqFundamentalData(contract, reportType="ReportSnapshot") or ""
    metrics = extract_metrics(parse_snapshot(snapshot_xml))
    growth, drawdown, volatility, positive_ratio = get_history_stats(ib, contract)
    sentiment, coverage, red_flags = get_sentiment(ib, contract.conId, news_items)

    moat = score_moat(metrics)
    quality = score_quality(metrics)
    predictability = score_predictability(growth, drawdown, volatility, positive_ratio)
    management = score_management(metrics, sentiment)
    risk = score_risk(red_flags, metrics["debt_to_equity"], drawdown)

    intrinsic, model_breakdown, margin = intrinsic_value_estimate(price, metrics, growth, moat, sentiment)
    rec = recommendation(margin, moat, quality, predictability, management, risk, sentiment)

    return DashboardData(
        price=price,
        metrics=metrics,
        history_growth=growth,
        drawdown=drawdown,
        volatility=volatility,
        positive_month_ratio=positive_ratio,
        sentiment=sentiment,
        sentiment_coverage=coverage,
        red_flags=red_flags,
        moat_score=moat,
        quality_score=quality,
        predictability_score=predictability,
        management_score=management,
        risk_score=risk,
        intrinsic_value=intrinsic,
        margin_of_safety=margin,
        recommendation=rec,
        model_breakdown=model_breakdown,
    )


def display_metric(name: str, value: Optional[float], percent: bool = False) -> None:
    if value is None:
        print(f"  {name:<28} N/A")
        return
    if percent:
        print(f"  {name:<28} {value * 100:>8.2f}%")
        return
    print(f"  {name:<28} {value:>10.3f}")


def display_dashboard(ticker: str, data: DashboardData) -> None:
    banner(f"BUFFETT-MUNGER DASHBOARD: {ticker}")
    print(f"  Current market price           {data.price:>10.2f}")
    if data.intrinsic_value is not None:
        print(f"  Intrinsic value estimate       {data.intrinsic_value:>10.2f}")
    else:
        print("  Intrinsic value estimate       N/A")
    if data.margin_of_safety is not None:
        print(f"  Margin of safety               {data.margin_of_safety * 100:>9.2f}%")
    else:
        print("  Margin of safety               N/A")
    print(f"  Recommendation                 {data.recommendation}")

    banner("1) BUFFETT FUNDAMENTAL QUALITY")
    display_metric("ROE", data.metrics["roe"], percent=True)
    display_metric("ROIC", data.metrics["roic"], percent=True)
    display_metric("Gross Margin", data.metrics["gross_margin"], percent=True)
    display_metric("Operating Margin", data.metrics["oper_margin"], percent=True)
    display_metric("Net Margin", data.metrics["net_margin"], percent=True)
    display_metric("Debt / Equity", data.metrics["debt_to_equity"])
    display_metric("Current Ratio", data.metrics["current_ratio"])
    display_metric("Interest Coverage", data.metrics["interest_cover"])

    banner("2) VALUE MODELS")
    display_metric("EPS (TTM proxy)", data.metrics["eps"])
    display_metric("Book Value / Share", data.metrics["bvps"])
    display_metric("P/E", data.metrics["pe"])
    display_metric("P/B", data.metrics["pb"])
    display_metric("Dividend Yield", data.metrics["dividend_yield"], percent=True)
    display_metric("10Y Price CAGR", data.history_growth, percent=True)
    if data.model_breakdown:
        for key in ("graham", "earnings_power", "owner_earnings", "book_anchor"):
            if key in data.model_breakdown:
                print(f"  Model[{key:<14}]          {data.model_breakdown[key]:>10.2f}")

    banner("3) MUNGER MENTAL MODEL SCORECARD")
    print(f"  Moat score (durability)        {data.moat_score:>10.3f}")
    print(f"  Quality score (economics)      {data.quality_score:>10.3f}")
    print(f"  Predictability score           {data.predictability_score:>10.3f}")
    print(f"  Management score               {data.management_score:>10.3f}")
    print(f"  Risk score (inversion)         {data.risk_score:>10.3f}")

    print("\n  Checklist:")
    print(f"  - Margin of safety >= 25%      {'PASS' if (data.margin_of_safety or -1) >= 0.25 else 'WARN'}")
    print(f"  - High quality economics       {'PASS' if data.quality_score >= 0.25 else 'WARN'}")
    print(f"  - Durable moat indicators      {'PASS' if data.moat_score >= 0.20 else 'WARN'}")
    print(f"  - Balance-sheet prudence       {'PASS' if data.risk_score >= 0 else 'WARN'}")
    print(f"  - Predictable compounding      {'PASS' if data.predictability_score >= 0.10 else 'WARN'}")
    print("  - Circle of competence         MANUAL CHECK")
    print("  - Incentives/management        PARTIAL (proxy only)")
    print("  - Opportunity-cost ranking     MANUAL CHECK")

    banner("4) SENTIMENT & NARRATIVE RISK")
    print(f"  Sentiment score (-1..+1)       {data.sentiment:>10.3f}")
    print(f"  News items scored              {data.sentiment_coverage:>10d}")
    print(f"  Narrative red-flag hits        {data.red_flags:>10d}")
    display_metric("Max drawdown (10Y)", data.drawdown, percent=True)
    display_metric("Monthly volatility", data.volatility, percent=True)
    display_metric("Positive month ratio", data.positive_month_ratio, percent=True)

    banner("5) INVESTMENT DECISION")
    print(f"  Final recommendation           {data.recommendation}")
    if data.recommendation in {"STRONG BUY", "BUY"}:
        print("  Thesis: valuation + quality + moat exceed risk constraints.")
    elif data.recommendation == "HOLD":
        print("  Thesis: mixed signal set; price near fair value or uncertain quality.")
    else:
        print("  Thesis: weak margin of safety or quality/risk profile not compelling.")

    banner("DISCLAIMER")
    print("  This dashboard is educational, not investment advice.")
    print("  Buffett/Munger principles require qualitative judgement beyond API data.")


def parse_args() -> Inputs:
    parser = argparse.ArgumentParser(description="Buffett/Munger-style valuation dashboard.")
    parser.add_argument("--ticker", required=True, help="Ticker symbol, e.g. AAPL")
    parser.add_argument("--live-data", action="store_true", help="Use live data type (default delayed).")
    parser.add_argument("--news-items", type=int, default=18, help="Number of news items for sentiment (default 18).")
    args = parser.parse_args()
    return Inputs(
        ticker=args.ticker.upper(),
        use_delayed_data=not args.live_data,
        news_items=clamp(float(args.news_items), 5, 40).__int__(),
    )


def main() -> None:
    util.startLoop()
    cfg = parse_args()

    banner("CONNECT")
    ib = IB()
    ib.connect(TWS_HOST, TWS_PORT, clientId=CLIENT_ID)
    print(f"Connected: {ib.isConnected()} | Server Time: {ib.reqCurrentTime()}")
    try:
        if cfg.use_delayed_data:
            ib.reqMarketDataType(3)
        data = collect_dashboard_data(ib, cfg.ticker, cfg.news_items)
        display_dashboard(cfg.ticker, data)
    finally:
        banner("DISCONNECT")
        ib.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
