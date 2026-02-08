"""
===============================================================================
 Interactive Brokers Value Investor Model
===============================================================================

Single-ticker valuation workflow using IB APIs:
  - Fundamental snapshot parsing
  - Historical trend/growth extraction
  - News headline + article sentiment scoring
  - Intrinsic value estimate + recommendation

Usage:
  python value_investor_model.py --ticker AAPL
===============================================================================
"""

from __future__ import annotations

import argparse
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ib_insync import IB, Stock, util


TWS_HOST = "127.0.0.1"
TWS_PORT = 7497
CLIENT_ID = 21


POSITIVE_WORDS = {
    "beat", "beats", "growth", "strong", "record", "upside", "surge", "profit",
    "profits", "improve", "improves", "improved", "expands", "expansion",
    "outperform", "outperformed", "bullish", "upgrade", "momentum",
}
NEGATIVE_WORDS = {
    "miss", "misses", "weak", "drop", "plunge", "decline", "declines", "downside",
    "warning", "warns", "loss", "losses", "lawsuit", "downgrade", "bearish",
    "investigation", "cut", "cuts", "slump", "recession",
}


@dataclass
class ModelInputs:
    ticker: str
    use_delayed_data: bool = True
    news_items: int = 12


@dataclass
class FundamentalSnapshot:
    metrics: Dict[str, float]

    def get_any(self, keys: Sequence[str]) -> Optional[float]:
        for key in keys:
            for name, value in self.metrics.items():
                if name.lower() == key.lower():
                    return value
        return None


def banner(title: str) -> None:
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


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


def normalize_percent(value: Optional[float]) -> Optional[float]:
    number = safe_float(value)
    if number is None:
        return None
    return number / 100.0 if abs(number) > 1 else number


def tokenize(text: str) -> List[str]:
    return re.findall(r"[A-Za-z']+", text.lower())


def parse_fundamental_snapshot(xml_text: str) -> FundamentalSnapshot:
    metrics: Dict[str, float] = {}
    if not xml_text:
        return FundamentalSnapshot(metrics=metrics)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return FundamentalSnapshot(metrics=metrics)

    name_keys = ("FieldName", "fieldName", "Name", "name", "Tag", "tag")
    value_keys = ("Value", "value", "v")

    for element in root.iter():
        metric_name = None
        for attr in name_keys:
            raw_name = element.attrib.get(attr)
            if raw_name:
                metric_name = str(raw_name).strip()
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

        parsed = safe_float(raw_value)
        if parsed is not None:
            metrics[metric_name] = parsed

    return FundamentalSnapshot(metrics=metrics)


def get_market_price(ib: IB, contract: Stock) -> Optional[float]:
    ticker = ib.reqMktData(contract, snapshot=True)
    ib.sleep(2)
    for value in (ticker.last, ticker.close, ticker.marketPrice(), ticker.bid, ticker.ask):
        parsed = safe_float(value)
        if parsed and parsed > 0:
            return parsed
    return None


def get_history_cagr(ib: IB, contract: Stock) -> Optional[float]:
    bars = ib.reqHistoricalData(
        contract=contract,
        endDateTime="",
        durationStr="5 Y",
        barSizeSetting="1 month",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    prices = [safe_float(b.close) for b in bars if safe_float(b.close)]
    if len(prices) < 24:
        return None
    first = prices[0]
    last = prices[-1]
    if not first or first <= 0 or not last or last <= 0:
        return None
    years = len(prices) / 12.0
    return (last / first) ** (1 / years) - 1


def get_news_sentiment(ib: IB, con_id: int, news_items: int) -> Tuple[float, int]:
    providers = ib.reqNewsProviders()
    if not providers:
        return 0.0, 0

    provider_codes = "+".join(p.code for p in providers[:3])
    headlines = ib.reqHistoricalNews(
        conId=con_id,
        providerCodes=provider_codes,
        startDateTime="",
        endDateTime="",
        totalResults=news_items,
    )
    if not headlines:
        return 0.0, 0

    score = 0.0
    seen = 0
    for headline in headlines:
        texts = [headline.headline or ""]
        try:
            article = ib.reqNewsArticle(headline.providerCode, headline.articleId)
            if article and article.articleText:
                texts.append(article.articleText[:1200])
        except Exception:
            pass

        words: List[str] = []
        for text in texts:
            words.extend(tokenize(text))
        if not words:
            continue

        positive = sum(1 for word in words if word in POSITIVE_WORDS)
        negative = sum(1 for word in words if word in NEGATIVE_WORDS)
        total = positive + negative
        if total == 0:
            continue
        score += (positive - negative) / total
        seen += 1

    if seen == 0:
        return 0.0, 0
    return max(-1.0, min(1.0, score / seen)), seen


def extract_core_fundamental_metrics(snapshot: FundamentalSnapshot) -> Dict[str, Optional[float]]:
    eps = snapshot.get_any(("EPS", "EPS_TTM", "TTMEPSXCLX", "DilutedEPSExclExtraTTM"))
    bvps = snapshot.get_any(("BookValuePerShare", "BVPS", "QBVPS"))
    pe = snapshot.get_any(("PERatio", "PE", "TTMPR2EPS"))
    pb = snapshot.get_any(("Price2Book", "PriceToBook", "PB"))
    roe = snapshot.get_any(("ReturnOnEquity", "ROE", "TTMROEPCT"))
    debt_to_equity = snapshot.get_any(("TotalDebtToEquity", "DebtToEquity", "LTDebt2Equity"))
    dividend_yield = snapshot.get_any(("DividendYield", "DivYield", "TTMDIVSHR"))
    return {
        "eps": eps,
        "bvps": bvps,
        "pe": pe,
        "pb": pb,
        "roe": normalize_percent(roe),
        "debt_to_equity": debt_to_equity,
        "dividend_yield": normalize_percent(dividend_yield),
    }


def compute_intrinsic_value(
    price: float,
    metrics: Dict[str, Optional[float]],
    history_cagr: Optional[float],
    sentiment_score: float,
) -> Tuple[Optional[float], Dict[str, float]]:
    eps = metrics["eps"]
    bvps = metrics["bvps"]
    roe = metrics["roe"]

    growth = history_cagr if history_cagr is not None else 0.05
    growth = max(-0.02, min(0.18, growth))
    growth_pct = growth * 100.0

    model_values: Dict[str, float] = {}

    if eps and eps > 0:
        graham = eps * (8.5 + 2 * growth_pct)
        model_values["graham"] = graham

        fair_pe = 12.0 + (6.0 * growth) + (4.0 * max(-0.2, min(0.25, sentiment_score)))
        fair_pe = max(8.0, min(24.0, fair_pe))
        model_values["earnings_power"] = eps * fair_pe

    if bvps and bvps > 0:
        fair_pb = 1.4
        if roe is not None:
            fair_pb += max(-0.4, min(0.8, (roe - 0.10) * 5))
        fair_pb += max(-0.2, min(0.2, sentiment_score * 0.2))
        fair_pb = max(0.7, min(3.0, fair_pb))
        model_values["book_value"] = bvps * fair_pb

    if not model_values:
        return None, {}

    weights = {
        "graham": 0.4,
        "earnings_power": 0.4,
        "book_value": 0.2,
    }
    active_weights = {k: weights[k] for k in model_values}
    total_weight = sum(active_weights.values())
    intrinsic = sum(model_values[k] * active_weights[k] for k in model_values) / total_weight

    diagnostics = {
        "growth_used": growth,
        "margin_of_safety": (intrinsic - price) / price if price > 0 else 0.0,
    }
    diagnostics.update(model_values)
    return intrinsic, diagnostics


def recommendation_from_scores(
    margin_of_safety: float,
    quality_score: float,
    sentiment_score: float,
) -> str:
    blended = (margin_of_safety * 0.65) + (quality_score * 0.25) + (sentiment_score * 0.10)
    if blended >= 0.20:
        return "STRONG BUY"
    if blended >= 0.08:
        return "BUY"
    if blended > -0.05:
        return "HOLD"
    if blended > -0.15:
        return "REDUCE"
    return "SELL"


def quality_score_from_fundamentals(metrics: Dict[str, Optional[float]]) -> float:
    score = 0.0
    roe = metrics["roe"]
    debt_to_equity = metrics["debt_to_equity"]
    pe = metrics["pe"]
    pb = metrics["pb"]
    div_yield = metrics["dividend_yield"]

    if roe is not None:
        score += max(-0.2, min(0.25, (roe - 0.10) * 1.5))
    if debt_to_equity is not None:
        score += max(-0.2, min(0.2, (1.0 - debt_to_equity) * 0.12))
    if pe is not None and pe > 0:
        score += max(-0.12, min(0.12, (18.0 - pe) * 0.01))
    if pb is not None and pb > 0:
        score += max(-0.08, min(0.08, (2.0 - pb) * 0.04))
    if div_yield is not None:
        score += max(0.0, min(0.05, div_yield * 0.5))

    return max(-0.5, min(0.5, score))


def print_metric(label: str, value: Optional[float], pct: bool = False) -> None:
    if value is None:
        print(f"  {label:<22} N/A")
        return
    if pct:
        print(f"  {label:<22} {value * 100:>8.2f}%")
    else:
        print(f"  {label:<22} {value:>10.2f}")


def parse_args() -> ModelInputs:
    parser = argparse.ArgumentParser(
        description="Run a value-investor-style valuation model from IB data."
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker, e.g. AAPL")
    parser.add_argument(
        "--live-data",
        action="store_true",
        help="Use live market data type (default is delayed market data).",
    )
    parser.add_argument(
        "--news-items",
        type=int,
        default=12,
        help="Number of historical headlines to analyze for sentiment (default: 12).",
    )
    args = parser.parse_args()
    return ModelInputs(
        ticker=args.ticker.upper(),
        use_delayed_data=not args.live_data,
        news_items=max(3, min(30, args.news_items)),
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

        contract = Stock(cfg.ticker, "SMART", "USD")
        ib.qualifyContracts(contract)

        banner(f"ANALYZING {cfg.ticker}")
        price = get_market_price(ib, contract)
        if not price:
            raise RuntimeError("Could not retrieve market price.")
        print(f"  Current price:           {price:.2f}")

        snapshot_xml = ib.reqFundamentalData(contract, reportType="ReportSnapshot") or ""
        snapshot = parse_fundamental_snapshot(snapshot_xml)
        metrics = extract_core_fundamental_metrics(snapshot)
        history_cagr = get_history_cagr(ib, contract)
        sentiment_score, sentiment_count = get_news_sentiment(ib, contract.conId, cfg.news_items)
        quality_score = quality_score_from_fundamentals(metrics)

        intrinsic, model_diag = compute_intrinsic_value(
            price=price,
            metrics=metrics,
            history_cagr=history_cagr,
            sentiment_score=sentiment_score,
        )

        banner("FUNDAMENTAL SNAPSHOT")
        print_metric("EPS (TTM)", metrics["eps"])
        print_metric("Book Value / Share", metrics["bvps"])
        print_metric("P/E", metrics["pe"])
        print_metric("P/B", metrics["pb"])
        print_metric("ROE", metrics["roe"], pct=True)
        print_metric("Debt / Equity", metrics["debt_to_equity"])
        print_metric("Dividend Yield", metrics["dividend_yield"], pct=True)
        print_metric("5Y Price CAGR (proxy)", history_cagr, pct=True)

        banner("SENTIMENT ANALYSIS")
        print(f"  News items scored:       {sentiment_count}")
        print(f"  Sentiment score:         {sentiment_score:>8.3f}  (-1 bearish, +1 bullish)")

        banner("VALUATION")
        if intrinsic is None:
            print("  Insufficient fundamental fields from IB ReportSnapshot for valuation.")
            print("  Try a different ticker or ensure fundamental entitlements are enabled.")
            return

        margin_of_safety = model_diag["margin_of_safety"]
        recommendation = recommendation_from_scores(margin_of_safety, quality_score, sentiment_score)

        print(f"  Intrinsic value estimate {intrinsic:>10.2f}")
        print(f"  Margin of safety         {margin_of_safety * 100:>9.2f}%")
        print(f"  Quality score            {quality_score:>9.3f}  (-0.5 to +0.5)")
        print(f"  Recommendation           {recommendation}")

        if "graham" in model_diag:
            print(f"  Model - Graham value     {model_diag['graham']:>10.2f}")
        if "earnings_power" in model_diag:
            print(f"  Model - Earnings power   {model_diag['earnings_power']:>10.2f}")
        if "book_value" in model_diag:
            print(f"  Model - Book value       {model_diag['book_value']:>10.2f}")

        banner("DISCLAIMER")
        print("  This is an educational model, not investment advice.")
        print("  Validate assumptions with full financial statements and your own research.")
    finally:
        banner("DISCONNECT")
        ib.disconnect()
        print("Disconnected.")


if __name__ == "__main__":
    main()
