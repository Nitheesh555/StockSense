"""
data/fundamentals.py - Scrape fundamental data from Screener.in (free).
Data is cached for 24 hours to avoid hammering the site.
"""

import requests
from bs4 import BeautifulSoup
from config import logger
from data.cache import get_fundamentals_cache, set_fundamentals_cache

SCREENER_URL = "https://www.screener.in/company/{symbol}/consolidated/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

FALLBACK_FUNDAMENTALS = {
    "pe_ratio": None,
    "roe": None,
    "debt_to_equity": None,
    "sales_growth_3yr": None,
    "profit_growth_3yr": None,
    "promoter_holding": None,
    "market_cap": None,
    "book_value": None,
    "dividend_yield": None,
    "current_ratio": None,
    "sector": "Unknown",
    "note": "Fundamentals unavailable",
}


def _parse_ratio(text: str):
    """Parse a ratio string like '23.4%' or '1,234.5' into float."""
    try:
        cleaned = text.strip().replace(",", "").replace("%", "").replace("Cr.", "").strip()
        return float(cleaned) if cleaned and cleaned not in ["-", "—", "N/A", ""] else None
    except (ValueError, AttributeError):
        return None


def fetch_fundamentals(symbol: str) -> dict:
    """
    Fetch key fundamental ratios for a NSE symbol from Screener.in.
    Returns a dict of metrics. Cached for 24 hours.
    """
    cached = get_fundamentals_cache(symbol)
    if cached:
        logger.debug("Fundamentals cache hit for %s", symbol)
        return cached

    url = SCREENER_URL.format(symbol=symbol)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 404:
            # Try standalone (non-consolidated) page
            url = url.replace("/consolidated/", "/")
            resp = requests.get(url, headers=HEADERS, timeout=15)

        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        result = {**FALLBACK_FUNDAMENTALS}

        # --- Key ratios section ---
        ratios_section = soup.find("section", id="top-ratios")
        if ratios_section:
            for li in ratios_section.find_all("li"):
                name_tag = li.find("span", class_="name")
                value_tag = li.find("span", class_="number")
                if not name_tag or not value_tag:
                    continue
                name = name_tag.get_text(strip=True).lower()
                value = _parse_ratio(value_tag.get_text(strip=True))

                if "p/e" in name:
                    result["pe_ratio"] = value
                elif "roe" in name:
                    result["roe"] = value
                elif "debt" in name and "equity" in name:
                    result["debt_to_equity"] = value
                elif "book value" in name:
                    result["book_value"] = value
                elif "dividend yield" in name:
                    result["dividend_yield"] = value
                elif "market cap" in name:
                    result["market_cap"] = value
                elif "current ratio" in name:
                    result["current_ratio"] = value

        # --- Promoter holding ---
        shareholding = soup.find("section", id="shareholding")
        if shareholding:
            rows = shareholding.find_all("tr")
            for row in rows:
                cells = row.find_all("td")
                if cells and "promoter" in cells[0].get_text(strip=True).lower():
                    # Last column is most recent quarter
                    result["promoter_holding"] = _parse_ratio(cells[-1].get_text(strip=True))
                    break

        # --- Compounded growth rates (3-year) ---
        growth_section = soup.find("section", id="profit-loss")
        if growth_section:
            tables = growth_section.find_all("table")
            for table in tables:
                for row in table.find_all("tr"):
                    cells = row.find_all("td")
                    if not cells:
                        continue
                    label = cells[0].get_text(strip=True).lower()
                    if "sales" in label and "growth" in label:
                        result["sales_growth_3yr"] = _parse_ratio(cells[-1].get_text(strip=True))
                    elif "profit" in label and "growth" in label:
                        result["profit_growth_3yr"] = _parse_ratio(cells[-1].get_text(strip=True))

        result.pop("note", None)
        set_fundamentals_cache(symbol, result)
        logger.info("Fetched fundamentals for %s: PE=%.1f, ROE=%.1f",
                    symbol,
                    result.get("pe_ratio") or 0,
                    result.get("roe") or 0)
        return result

    except Exception as e:
        logger.warning("Fundamentals fetch failed for %s: %s", symbol, e)
        return FALLBACK_FUNDAMENTALS


def format_fundamentals_for_prompt(fundamentals: dict) -> str:
    """Format fundamentals dict into a readable string for the AI prompt."""
    lines = []
    field_labels = {
        "pe_ratio": "P/E Ratio",
        "roe": "ROE (%)",
        "debt_to_equity": "Debt/Equity",
        "sales_growth_3yr": "3yr Sales Growth (%)",
        "profit_growth_3yr": "3yr Profit Growth (%)",
        "promoter_holding": "Promoter Holding (%)",
        "market_cap": "Market Cap (Cr)",
        "book_value": "Book Value",
        "dividend_yield": "Dividend Yield (%)",
        "current_ratio": "Current Ratio",
    }
    for key, label in field_labels.items():
        val = fundamentals.get(key)
        lines.append(f"  {label}: {val if val is not None else 'N/A'}")
    return "\n".join(lines)
