from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, List, Tuple

from bs4 import BeautifulSoup
from dotenv import load_dotenv

# --- HELPER FUNCTIONS ---

def _j(d: Dict[str, Any]) -> str:
    return json.dumps(d, ensure_ascii=False)


def _slugify(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[^\w\s-]", "", t)   # remove punctuation
    t = re.sub(r"\s+", "-", t)       # spaces -> hyphen
    t = re.sub(r"-+", "-", t)        # collapse hyphens
    return t.strip("-")


def _extract_money(text: str) -> Optional[float]:
    """
    Extracts the first float number from a string like 'Rs 4,500.50 / Quintal'.
    Returns 4500.5. Returns None if no number found.
    """
    if not text:
        return None
    # Remove commas to handle '1,200'
    cleaned = text.replace(",", "")
    # Find number (int or float)
    m = re.search(r"(\d+(?:\.\d+)?)", cleaned)
    return float(m.group(1)) if m else None


def _fetch_with_selenium(url: str, timeout_sec: int = 25) -> Tuple[Optional[str], Optional[str]]:
    """
    Fetch page HTML using Selenium.
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.support.ui import WebDriverWait
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
    except ImportError:
        return None, "selenium_not_installed"

    driver = None
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        )

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.get(url)

        # Wait for table or price update text
        WebDriverWait(driver, timeout_sec).until(
            lambda d: ("table" in d.page_source) or ("Price updated" in d.page_source)
        )

        html = driver.page_source
        return html, None

    except Exception as e:
        return None, f"selenium_error: {str(e)}"

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass


def _parse_commodityonline_html(html: str) -> Dict[str, Any]:
    """
    Robust Table Parser.
    1. Finds the table.
    2. Maps column headers (e.g. 'Min Price', 'Avg Price') to indices.
    3. Ignores 'Arrival' or 'Quantity' columns to prevent data mix-up.
    """
    soup = BeautifulSoup(html, "lxml")
    
    # --- 1. Get "Last Updated" Date ---
    price_updated = None
    # Look for text like "Price updated : 05 Feb '26"
    upd_node = soup.find(string=re.compile(r"Price updated", re.IGNORECASE))
    if upd_node:
        # Clean up the string
        clean_text = upd_node.replace("Price updated", "").replace(":", "").strip()
        price_updated = clean_text

    # --- 2. Find and Parse the Table ---
    rows_data = []
    
    # Find all tables, we usually want the one with 'Price' in headers
    tables = soup.find_all("table")
    target_table = None
    
    for t in tables:
        headers_text = t.get_text().lower()
        if "price" in headers_text or "min" in headers_text:
            target_table = t
            break
    
    if target_table:
        # Extract headers to map indices
        headers = [th.get_text(strip=True).lower() for th in target_table.find_all("th")]
        
        # Helper to find column index
        def get_col_idx(keywords):
            for i, h in enumerate(headers):
                if any(k in h for k in keywords):
                    return i
            return -1

        # Map critical columns
        idx_date = get_col_idx(["date", "arrival"])
        idx_min  = get_col_idx(["min", "lowest"])
        idx_max  = get_col_idx(["max", "costliest", "highest"])
        idx_avg  = get_col_idx(["avg", "average", "modal"])

        # Parse rows (skip header)
        tbody = target_table.find("tbody") or target_table
        tr_list = tbody.find_all("tr")
        
        for tr in tr_list:
            cells = tr.find_all("td")
            # Need enough cells to cover our max index
            max_needed = max(idx_date, idx_min, idx_max, idx_avg)
            if not cells or len(cells) <= max_needed:
                continue

            # Extract text safely
            r_date = cells[idx_date].get_text(strip=True) if idx_date != -1 else ""
            r_min  = _extract_money(cells[idx_min].get_text()) if idx_min != -1 else None
            r_max  = _extract_money(cells[idx_max].get_text()) if idx_max != -1 else None
            r_avg  = _extract_money(cells[idx_avg].get_text()) if idx_avg != -1 else None

            # Only add valid rows (must have at least one price)
            if r_min or r_max or r_avg:
                rows_data.append({
                    "arrival_date": r_date,
                    "min_price_quintal": r_min,
                    "max_price_quintal": r_max,
                    "avg_price_quintal": r_avg
                })

    # --- 3. Determine Final Stats ---
    # We prefer the top row (most recent) from the table
    avg_val, min_val, max_val = None, None, None

    if rows_data:
        latest = rows_data[0]
        avg_val = latest.get("avg_price_quintal")
        min_val = latest.get("min_price_quintal")
        max_val = latest.get("max_price_quintal")
        
        # If updated date was not found in banner, use the date from the row
        if not price_updated:
            price_updated = latest.get("arrival_date")

    # Fallback: If table failed, try the "Summary Card" logic (Regex)
    if not avg_val:
        page_text = soup.get_text(" ", strip=True)
        # Look for "Average Price ₹ 4500" pattern
        m_avg = re.search(r"Average Price\s*₹?\s*(\d+(?:,\d+)?(?:.\d+)?)", page_text, re.IGNORECASE)
        if m_avg: avg_val = _extract_money(m_avg.group(1))
        
        m_min = re.search(r"Lowest Market Price\s*₹?\s*(\d+(?:,\d+)?(?:.\d+)?)", page_text, re.IGNORECASE)
        if m_min: min_val = _extract_money(m_min.group(1))

        m_max = re.search(r"Costliest Market Price\s*₹?\s*(\d+(?:,\d+)?(?:.\d+)?)", page_text, re.IGNORECASE)
        if m_max: max_val = _extract_money(m_max.group(1))

    # Identify missing data
    missing = []
    if avg_val is None: missing.append("avg_price_not_found")
    if min_val is None: missing.append("min_price_not_found")

    return {
        "avg_price_quintal": avg_val,
        "min_price_quintal": min_val,
        "max_price_quintal": max_val,
        "price_updated": price_updated,
        "rows": rows_data[:5], # Return top 5 rows
        "missing_data": missing,
    }


@dataclass
class MarketTool:
    name: str = "market_tool"
    base_url: str = "https://www.commodityonline.com/mandiprices"
    polite_sleep_sec: float = 0.5

    def run(self, inputs: Optional[Dict[str, Any]] = None) -> str:
        load_dotenv()
        inputs = inputs or {}

        commodity = inputs.get("commodity")
        state = inputs.get("state")
        market = inputs.get("market")

        if not (commodity and state and market):
            return _j({
                "tool": self.name,
                "status": "missing_data",
                "message": "Required: commodity, state, market",
                "data": {}
            })

        # Construct URL
        c_slug = _slugify(str(commodity))
        s_slug = _slugify(str(state))
        m_slug = _slugify(str(market))
        url = f"{self.base_url}/{c_slug}/{s_slug}/{m_slug}"

        time.sleep(self.polite_sleep_sec)

        # Fetch
        html, err = _fetch_with_selenium(url)
        if err or not html:
            return _j({
                "tool": self.name,
                "status": "error",
                "message": f"Fetch failed: {err}",
                "data": {"url": url},
                "sources": [url]
            })

        # Parse
        parsed = _parse_commodityonline_html(html)
        
        status = "ok"
        if parsed.get("missing_data"):
            # It's only a hard error if we found absolutely nothing
            if parsed["avg_price_quintal"] is None:
                status = "error"
                msg = "Could not find price in table or summary."
            else:
                status = "ok" # Partial data is okay
                msg = "Partial data found."
        else:
            msg = "Mandi price fetched successfully."

        return _j({
            "tool": self.name,
            "status": status,
            "message": msg,
            "inputs_received": inputs,
            "data": {"url": url, **parsed},
            "sources": [url]
        })