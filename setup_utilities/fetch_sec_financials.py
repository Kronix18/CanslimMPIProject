#!/usr/bin/env python3
"""
fetch_sec_financials.py — Fetch SEC EDGAR financial data for all S&P 500 stocks.

This script populates the financials table by:
1. Loading the universe from database
2. For each company, fetching SEC XBRL facts via data_collection.collect_sec_facts()
3. Writing financial rows to database
4. Respecting SEC rate limits (0.12 seconds between requests)

This enables the "C" (EPS growth) and "A" (ROE) CAN SLIM factors.

Usage:
    python fetch_sec_financials.py [--limit N]  # Fetch N companies (default: all)
    python fetch_sec_financials.py --limit 10   # Fetch only first 10
"""

import argparse
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))

from data_collection import collect_sec_facts
from repository import RepositoryFactory


def main():
    """Fetch SEC financials for universe of stocks."""
    
    parser = argparse.ArgumentParser(description="Fetch SEC EDGAR financials for S&P 500")
    parser.add_argument("--limit", type=int, default=None, help="Limit to N companies (for testing)")
    args = parser.parse_args()
    
    print("\n" + "="*70)
    print("FETCHING SEC FINANCIAL DATA FOR S&P 500")
    print("="*70 + "\n")
    
    # Load configuration
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    repo = RepositoryFactory.from_config(config)
    
    # Load universe
    print("Loading universe from database...")
    universe = repo.read_universe()
    if universe is None or universe.empty:
        print("ERROR: Universe table is empty. Run rebuild_universe.py first.")
        return 1
    
    # Extract ticker/CIK pairs
    universe_records = []
    for idx, row in universe.iterrows():
        universe_records.append({
            "ticker": row.get("ticker"),
            "cik": row.get("cik"),
            "name": row.get("name"),
        })
    
    if args.limit:
        universe_records = universe_records[:args.limit]
    
    print(f"Fetching financials for {len(universe_records)} companies...")
    print("(This may take several minutes due to SEC rate limits)\n")
    
    # Fetch financials for each company
    success_count = 0
    error_count = 0
    
    for i, rec in enumerate(universe_records, 1):
        ticker = rec["ticker"]
        cik = rec["cik"]
        name = rec["name"]
        
        try:
            print(f"[{i:3d}/{len(universe_records)}] {ticker:8} | {name[:40]:40}", end=" ... ")
            
            # Fetch SEC facts
            facts = collect_sec_facts(
                cik=cik,
                ticker=ticker,
                config=config,
                repo=repo,
                force_refresh=False,  # Use cache if available
            )
            
            if facts:
                print(f"✓ {len(facts)} financial rows")
                success_count += 1
            else:
                print("⊘ No financials found")
            
        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
            break
        except Exception as e:
            print(f"✗ Error: {str(e)[:30]}")
            error_count += 1
            continue
    
    print("\n" + "="*70)
    print(f"RESULTS")
    print("="*70)
    print(f"Success:       {success_count}/{len(universe_records)}")
    print(f"Errors:        {error_count}/{len(universe_records)}")
    
    # Verify financials were written
    fin_count = 0
    try:
        # Quick check on sample tickers
        sample_tickers = [r["ticker"] for r in universe_records[:5]]
        for ticker in sample_tickers:
            fins = repo.read_financials(ticker, is_annual=None)
            if fins is not None and len(fins) > 0:
                fin_count += len(fins)
    except:
        pass
    
    if fin_count > 0:
        print(f"Financials in DB: {fin_count} rows (sample check)")
    
    print("="*70 + "\n")
    
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
