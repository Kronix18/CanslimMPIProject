#!/usr/bin/env python3
"""
populate_universe.py — Load S&P 500 universe into database.

This script fetches S&P 500 tickers from Wikipedia and populates the universe table
with ticker metadata. Run this ONCE to initialize the universe table.
"""

import sys
from pathlib import Path
import yaml

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from repository import RepositoryFactory
from universe import load_sp500_tickers
from schemas import UniverseRecord

def main():
    """Load S&P 500 tickers into universe table."""
    print("Populating universe table with S&P 500 tickers...")
    
    # Load configuration
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    repo = RepositoryFactory.from_config(config)
    
    # Fetch S&P 500 tickers
    print("  Fetching S&P 500 tickers from Wikipedia...")
    tickers = load_sp500_tickers()
    print(f"  Fetched {len(tickers)} tickers")
    
    if not tickers:
        print("ERROR: Could not fetch tickers!")
        return 1
    
    # Create UniverseRecord for each ticker
    print(f"  Creating {len(tickers)} universe records...")
    records = []
    for ticker in sorted(tickers):
        record = UniverseRecord(
            ticker=ticker,
            name=ticker,  # Use ticker as placeholder name
            cik="0000000000",  # Placeholder CIK
        )
        records.append(record)
    
    # Write all records at once
    print(f"  Writing {len(records)} records to universe table...")
    repo.write_universe(records)
    
    # Verify
    universe = repo.read_universe()
    actual_count = len(universe) if universe is not None else 0
    print(f"\n✓ Universe table populated with {actual_count} records")
    
    if actual_count == 0:
        print("WARNING: Universe table is still empty!")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
