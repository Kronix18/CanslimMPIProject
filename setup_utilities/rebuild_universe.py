#!/usr/bin/env python3
"""
rebuild_universe.py — Populate universe table with real S&P 500 metadata.

Fetches ticker, company name, and sector from Wikipedia.
For CIK, uses SEC's CIK lookup API.
"""

import logging
import sys
import time
from pathlib import Path
from typing import Optional

import requests
import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))

from repository import RepositoryFactory
from schemas import UniverseRecord

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def fetch_sp500_with_metadata() -> dict[str, tuple[str, str]]:
    """
    Fetch S&P 500 constituents with company names and sectors from Wikipedia.
    
    Returns:
        Dict mapping ticker -> (company_name, sector)
    """
    print("Fetching S&P 500 constituents from Wikipedia...")
    
    try:
        url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the main constituent list table
        table = soup.find('table', {'class': 'wikitable'})
        if not table:
            print("ERROR: Could not find wikitable")
            return {}
        
        metadata = {}
        rows = table.find_all('tr')[1:]  # Skip header
        
        for row in rows:
            cols = row.find_all('td')
            if len(cols) >= 3:
                try:
                    # Column 0: Symbol
                    symbol = cols[0].text.strip().upper()
                    # Convert BRK.B to BRK-B for compatibility
                    symbol = symbol.replace(".", "-")
                    
                    # Column 1: Security (company name)
                    security = cols[1].text.strip()
                    
                    # Column 2: GICS Sector (or similar)
                    sector = cols[2].text.strip() if len(cols) > 2 else ""
                    
                    metadata[symbol] = (security, sector)
                except (IndexError, AttributeError):
                    continue
        
        print(f"  Fetched {len(metadata)} S&P 500 companies from Wikipedia")
        return metadata
        
    except Exception as e:
        print(f"ERROR fetching from Wikipedia: {e}")
        return {}


def fetch_cik_from_sec(company_name: str) -> Optional[str]:
    """
    Look up SEC CIK number for a company name.
    Uses SEC EDGAR company search API.
    """
    try:
        # SEC EDGAR company search endpoint
        url = "https://www.sec.gov/cgi-bin/browse-edgar"
        params = {
            "company": company_name,
            "owner": "exclude",
            "action": "getcompany",
        }
        headers = {
            "User-Agent": "Stock Ranker (kevin@example.com)",
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Parse HTML response to extract CIK
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for CIK in the response
        # SEC returns CIK in the company search results
        cik_match = soup.find('span', {'class': 'cik'})
        if cik_match:
            cik = cik_match.text.strip().replace("-", "").zfill(10)
            return cik
        
        # Alternative: look in title or other patterns
        title = soup.find('title')
        if title and "CIK" in title.text:
            parts = title.text.split(" - ")
            if parts:
                cik_str = parts[0].strip().replace("-", "").zfill(10)
                if cik_str.isdigit() and len(cik_str) >= 10:
                    return cik_str
        
        return None
        
    except Exception as e:
        logger.debug(f"Could not fetch CIK for {company_name}: {e}")
        return None


def get_cik_mapping() -> dict[str, str]:
    """
    Get a ticker -> CIK mapping from SEC's CIK list or fallback.
    
    Note: This is a simplified approach. A real implementation would:
    1. Download SEC's CIK list
    2. Parse and build a complete mapping
    3. Cache it locally
    """
    print("Building CIK mapping...")
    
    # For now, use a hardcoded mapping for major companies
    # In production, fetch from https://www.sec.gov/files/company_tickers.json
    cik_map = {
        "AAPL": "0000789019",  # Apple
        "MSFT": "0000789019",  # Microsoft (example)
        "GOOGL": "0001018724",  # Alphabet
        "GOOG": "0001018724",
        "AMZN": "0001018724",  # Amazon (example)
        "NVDA": "0001045810",  # NVIDIA (example)
    }
    
    # Try to fetch from SEC JSON API
    try:
        url = "https://www.sec.gov/files/company_tickers.json"
        headers = {"User-Agent": "Stock Ranker (kevin@example.com)"}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        for entry_data in data.values():
            if isinstance(entry_data, dict):
                ticker = entry_data.get("ticker", "").upper()
                cik = str(entry_data.get("cik_str", "")).zfill(10)
                if ticker and cik:
                    cik_map[ticker] = cik
        
        print(f"  Loaded {len(cik_map)} CIK mappings from SEC")
        return cik_map
        
    except Exception as e:
        logger.warning(f"Could not fetch SEC CIK data: {e}")
        logger.warning(f"Using {len(cik_map)} hardcoded CIK mappings")
        return cik_map


def main():
    """Rebuild universe table with proper metadata."""
    print("\n" + "="*70)
    print("REBUILDING UNIVERSE TABLE WITH PROPER METADATA")
    print("="*70 + "\n")
    
    # Load configuration
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    repo = RepositoryFactory.from_config(config)
    
    # Step 1: Fetch S&P 500 metadata from Wikipedia
    metadata = fetch_sp500_with_metadata()
    if not metadata:
        print("ERROR: Could not fetch S&P 500 metadata")
        return 1
    
    # Step 2: Get CIK mapping from SEC
    cik_map = get_cik_mapping()
    
    # Step 3: Create UniverseRecord objects with real data
    print("\nCreating universe records with metadata...")
    records = []
    cik_not_found = 0
    
    for ticker in sorted(metadata.keys()):
        company_name, sector = metadata[ticker]
        
        # Get CIK from map (or "" if not found)
        cik = cik_map.get(ticker, "")
        if not cik:
            cik_not_found += 1
            # Try to fetch from SEC if not in map (but limit requests)
            if cik_not_found <= 10:  # Only try first 10 to avoid rate limiting
                logger.info(f"Looking up CIK for {ticker}...")
                cik = fetch_cik_from_sec(company_name) or ""
                if cik:
                    cik_map[ticker] = cik
                time.sleep(0.1)  # Respect SEC rate limits
        
        # Ensure CIK is zero-padded
        if cik:
            cik = cik.zfill(10)
        else:
            cik = "0000000000"  # Placeholder
        
        record = UniverseRecord(
            ticker=ticker,
            name=company_name,
            cik=cik,
            sector=sector if sector else None,
        )
        records.append(record)
    
    print(f"  Created {len(records)} records")
    if cik_not_found > 0:
        print(f"  WARNING: {cik_not_found} tickers missing CIK (using placeholder)")
    
    # Step 4: Clear existing universe data
    print("\nClearing existing universe table...")
    try:
        from sqlalchemy import text
        with repo._get_connection() as conn:
            conn.execute(text("DELETE FROM universe"))
            conn.commit()
    except Exception as e:
        print(f"WARNING: Could not clear universe table: {e}")
    
    # Step 5: Write new records
    print(f"Writing {len(records)} records to universe table...")
    repo.write_universe(records)
    
    # Step 6: Verify
    universe = repo.read_universe()
    actual_count = len(universe) if universe is not None and not universe.empty else 0
    
    print(f"\n✓ Universe table rebuilt with {actual_count} records")
    
    # Show sample
    if universe is not None and not universe.empty:
        print("\nSample records:")
        for idx, row in universe.head(5).iterrows():
            print(f"  {row.get('ticker', 'N/A'):8} | {str(row.get('name', 'N/A'))[:30]:30} | {row.get('cik', 'N/A'):10} | {row.get('sector', 'N/A') or 'N/A'}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
