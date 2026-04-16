"""
Fetch the full US equity + ETF universe from NASDAQ screener and etfdb.com.
Outputs stock_universe_full.csv with market cap, sector, ETF flags, etc.

Run once per day before market open, e.g.:
    python ticker_universe.py

The dashboard's main.py reads stock_universe_full.csv at startup to:
  - Exclude all ETFs and the top 100 stocks by market cap from the SIP stream
  - Apply tiered volume-spike thresholds (nano / small / mid) based on market cap
"""

import requests
import pandas as pd
import time
import logging

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# SOURCE 2A: NASDAQ ETF screener (separate endpoint)
# This includes NYSE Arca ETFs like SPY, QQQ, IVV
# ─────────────────────────────────────────────

def get_all_etfs_nasdaq() -> pd.DataFrame:
    """
    NASDAQ has a separate /etf endpoint that covers NYSE Arca ETFs.
    This is where SPY, QQQ, IVV, GLD, etc. live.
    """
    url = "https://api.nasdaq.com/api/screener/etf"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    params = {"limit": 25, "offset": 0, "download": "true"}

    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rows = data.get("data", {}).get("data", {}).get("rows", [])
    # fallback path
    if not rows:
        rows = data.get("data", {}).get("rows", [])

    logger.info(f"Fetched {len(rows)} ETFs from NASDAQ ETF screener")

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    col_map = {
        "symbol": "ticker",
        "companyName": "company_name",
        "name": "company_name",
        "lastSalePrice": "last_price",
        "netChange": "net_change",
        "percentChange": "pct_change",
        "volume": "volume",
        "country": "country",
        "marketCap": "market_cap_raw",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    df["sector"] = ""
    df["industry"] = ""
    df["quote_type"] = "ETF"   # we know these are ETFs

    return df


# ─────────────────────────────────────────────
# SOURCE 2B: ETF.com bulk download (most complete)
# Covers ALL US-listed ETFs including leveraged/inverse
# ─────────────────────────────────────────────

def get_etfs_from_etfdb() -> pd.DataFrame:
    """
    ETF Database (etfdb.com) free screener — returns 2000+ ETFs
    with asset class, category (identifies leveraged/inverse), AUM.
    """
    url = "https://etfdb.com/api/screener/"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://etfdb.com/screener/",
        "X-Requested-With": "XMLHttpRequest",
    }

    all_rows = []
    page = 1

    while True:
        payload = {
            "page": page,
            "per_page": 250,
            "only": ["meta", "data"],
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"etfdb page {page} failed: {e}")
            break

        rows = data.get("data", [])
        if not rows:
            break

        all_rows.extend(rows)
        total_pages = data.get("meta", {}).get("total_pages", 1)
        logger.info(f"etfdb page {page}/{total_pages} — {len(all_rows)} ETFs so far")

        if page >= total_pages:
            break
        page += 1
        time.sleep(0.5)

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # etfdb returns nested dicts per field — extract the display value
    def extract_val(cell):
        if isinstance(cell, dict):
            return cell.get("text") or cell.get("value") or cell.get("display_value")
        return cell

    for col in df.columns:
        df[col] = df[col].apply(extract_val)

    col_map = {
        "symbol": "ticker",
        "fund_name": "company_name",
        "name": "company_name",
        "aum": "aum",
        "asset_class": "etf_asset_class",
        "category": "etf_category",
        "ytd_return": "ytd_return",
        "avg_volume": "volume",
        "expense_ratio": "expense_ratio",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    df["quote_type"] = "ETF"
    df["sector"] = ""

    logger.info(f"Total ETFs from etfdb: {len(df)}")
    return df


# ─────────────────────────────────────────────
# Enhanced classifier
# ─────────────────────────────────────────────

LEVERAGED_KEYWORDS = [
    " 2x", " 3x", "-2x", "-3x", "x leveraged", "ultrashort", "ultrapro", "ultra pro",
    "leveraged", "daily bull", "daily bear", "direxion daily",
    "proshares ultra", "bull 2x", "bull 3x", "bear 2x", "bear 3x",
]

INVERSE_KEYWORDS = [
    "inverse", "short ", "bear", "ultrashort",
    "daily bear", "-1x", "-2x", "-3x",
]

ETF_ISSUER_KEYWORDS = [
    "ishares", "vanguard", "spdr",
    "invesco q", "invesco s", "invesco b", "invesco e", "invesco f",
    "invesco trust", "invesco fund", "invesco etf", "invesco dynamic",
    "invesco db ", "invesco senior",
    "wisdomtree ",
    "global x", "first trust", "schwab etf",
    " ark etf", "ark innovation", "ark genomic", "ark next", "ark fintech", "ark space",
    "vaneck", "xtrackers", "pacer", "amplify", "direxion", "proshares",
    "innovator", "roundhill", "defiance", "simplify", " etf",
]

REIT_NAME_SIGNALS = [
    "reit", "realty", " properties", " property",
    "real estate investment trust", "real estate trust",
]


def classify_instrument_v2(row: dict) -> str:
    name = str(row.get("company_name", "") or "").lower()
    quote_type = str(row.get("quote_type", "") or "").lower()
    etf_category = str(row.get("etf_category", "") or "").lower()
    etf_asset_class = str(row.get("etf_asset_class", "") or "").lower()
    sector = str(row.get("sector", "") or "").lower()
    market_cap = row.get("market_cap")
    is_known_etf = bool(row.get("_is_known_etf", False))

    is_etf_signal = is_known_etf or quote_type == "etf" or "etf" in etf_category

    if is_etf_signal:
        if "leveraged" in etf_category or any(kw in name for kw in LEVERAGED_KEYWORDS):
            return "Leveraged ETF"
        if "inverse" in etf_category or any(kw in name for kw in INVERSE_KEYWORDS):
            return "Inverse ETF"
        return "ETF"

    if quote_type == "mutualfund":
        return "Mutual Fund"

    if not sector:
        if any(kw in name for kw in LEVERAGED_KEYWORDS):
            return "Leveraged ETF"
        if any(kw in name for kw in INVERSE_KEYWORDS) and any(kw in name for kw in ETF_ISSUER_KEYWORDS):
            return "Inverse ETF"
        if any(kw in name for kw in ETF_ISSUER_KEYWORDS):
            return "ETF"

    if sector == "real estate" and any(sig in name for sig in REIT_NAME_SIGNALS):
        return "REIT"
    if any(sig in name for sig in ["reit", "real estate investment trust"]):
        return "REIT"

    if "business development" in name or " bdc" in name:
        return "BDC"
    if any(kw in name for kw in [" fund", "closed-end", "interval fund"]):
        return "Fund"

    has_market_cap = market_cap is not None and not (
        isinstance(market_cap, float) and pd.isna(market_cap)
    )
    if not has_market_cap and not sector:
        return "ETF/Fund (unclassified)"

    return "Stock"


def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    df["instrument_type"] = df.apply(lambda r: classify_instrument_v2(r.to_dict()), axis=1)
    df["is_etf"]           = df["instrument_type"].isin(["ETF", "Leveraged ETF", "Inverse ETF", "ETF/Fund (unclassified)"])
    df["is_leveraged_etf"] = df["instrument_type"] == "Leveraged ETF"
    df["is_inverse_etf"]   = df["instrument_type"] == "Inverse ETF"
    df["is_fund"]          = df["instrument_type"].isin(["Fund", "Mutual Fund", "Money Market"])
    df["is_reit"]          = df["instrument_type"] == "REIT"
    df["is_bdc"]           = df["instrument_type"] == "BDC"
    df["is_stock"]         = df["instrument_type"] == "Stock"
    return df


# ─────────────────────────────────────────────
# STEP 1: Stock universe (NASDAQ screener)
# ─────────────────────────────────────────────

def get_all_tickers_nasdaq() -> pd.DataFrame:
    url = "https://api.nasdaq.com/api/screener/stocks"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    params = {"tableonly": "true", "limit": 25, "offset": 0, "download": "true"}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    rows = data.get("data", {}).get("rows", [])
    total = data.get("data", {}).get("total", {}).get("recordTotal", len(rows))

    if len(rows) < total:
        for offset in range(25, total, 25):
            params["offset"] = offset
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code == 200:
                rows.extend(r.json().get("data", {}).get("rows", []))
            time.sleep(0.3)

    df = pd.DataFrame(rows).rename(columns={
        "symbol": "ticker", "name": "company_name",
        "marketCap": "market_cap_raw", "sector": "sector",
        "industry": "industry", "lastsale": "last_price",
        "country": "country", "ipoyear": "ipo_year", "volume": "volume",
    })

    def parse_mcap(val):
        if pd.isna(val) or not val:
            return None
        val = str(val).replace("$", "").replace(",", "").strip()
        for suffix, mult in [("T", 1e12), ("B", 1e9), ("M", 1e6), ("K", 1e3)]:
            if val.endswith(suffix):
                try: return float(val[:-1]) * mult
                except: return None
        try: return float(val)
        except: return None

    if "market_cap_raw" in df.columns:
        df["market_cap"] = df["market_cap_raw"].apply(parse_mcap)
        df.drop(columns=["market_cap_raw"], inplace=True)

    df["quote_type"] = ""
    df["etf_category"] = ""
    df["etf_asset_class"] = ""
    logger.info(f"Stocks: {len(df)} rows")
    return df


# ─────────────────────────────────────────────
# MAIN: Merge all sources
# ─────────────────────────────────────────────

def _is_missing(v) -> bool:
    if v is None or v == "":
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    return False


def build_full_universe() -> pd.DataFrame:
    # 1. Stocks (NYSE/NASDAQ/AMEX)
    stocks_df = get_all_tickers_nasdaq()

    # 2. ETFs from NASDAQ ETF endpoint
    etf_nasdaq_df = get_all_etfs_nasdaq()

    # 3. ETFs from etfdb (most complete)
    etf_db_df = get_etfs_from_etfdb()

    # Build definitive ETF ticker set BEFORE merging
    etf_tickers: set[str] = set()
    for _df in [etf_nasdaq_df, etf_db_df]:
        if not _df.empty and "ticker" in _df.columns:
            etf_tickers |= set(_df["ticker"].dropna().str.upper().str.strip())

    stocks_df["_source_priority"] = 0
    etf_nasdaq_df["_source_priority"] = 1
    etf_db_df["_source_priority"] = 2

    base_cols = [
        "ticker", "company_name", "market_cap", "sector",
        "industry", "last_price", "volume", "country",
        "quote_type", "etf_category", "etf_asset_class",
        "_source_priority",
    ]

    def align(df: pd.DataFrame) -> pd.DataFrame:
        for c in base_cols:
            if c not in df.columns:
                df[c] = None
        return df[base_cols].copy()

    combined = pd.concat(
        [align(stocks_df), align(etf_nasdaq_df), align(etf_db_df)],
        ignore_index=True,
    )

    combined["_data_score"] = combined.apply(
        lambda r: sum(1 for v in r if not _is_missing(v)), axis=1
    )

    combined = (
        combined
        .sort_values(["_source_priority", "_data_score"], ascending=[False, False])
        .drop_duplicates(subset=["ticker"], keep="first")
        .drop(columns=["_data_score", "_source_priority"])
        .reset_index(drop=True)
    )

    combined["_is_known_etf"] = (
        combined["ticker"].str.upper().str.strip().isin(etf_tickers)
    )

    combined = add_flags(combined)
    combined = combined.drop(columns=["_is_known_etf"], errors="ignore")
    combined = combined.sort_values("market_cap", ascending=False, na_position="last")

    combined.to_csv("stock_universe_full.csv", index=False)
    logger.info(f"Full universe: {len(combined)} instruments saved to stock_universe_full.csv")

    # Summary
    print("\n── Instrument Breakdown ──")
    print(combined["instrument_type"].value_counts().to_string())

    etf_count  = combined["is_etf"].sum()
    stock_count = combined["is_stock"].sum()
    top100 = combined[combined["is_stock"]].nlargest(100, "market_cap")
    print(f"\n── Exclusion preview ──")
    print(f"  ETFs to exclude:          {etf_count}")
    print(f"  Top-100 stocks to exclude:{len(top100)}")
    print(f"  Top-100 tickers: {list(top100['ticker'].head(20))} …")

    print("\n── SPY / QQQ / IVV / VISA check ──")
    spot_check = combined[combined["ticker"].isin(["SPY", "QQQ", "IVV", "GLD", "TQQQ", "SQQQ", "NVDA", "AAPL", "V"])]
    print(spot_check[["ticker", "company_name", "instrument_type", "is_etf", "is_leveraged_etf", "is_stock"]].to_string(index=False))

    return combined


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    print("Building full stock + ETF universe…")
    df = build_full_universe()
    print(f"\nDone. {len(df)} total instruments written to stock_universe_full.csv")
