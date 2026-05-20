#!/usr/bin/env python3
"""
load_stooq_data.py — Load raw stooq CSV files into the database.

This script finds all .txt files in data/raw/stooq/data/daily/us
and loads them as price bars, FILTERING TO S&P 500 STOCKS ONLY.

Usage:
    python load_stooq_data.py
"""

import logging
from datetime import datetime
from pathlib import Path

import yaml

from repository import RepositoryFactory
from schemas import DataSource, PriceBar
from universe import load_sp500_tickers

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_config(config_path: Path = None) -> dict:
    """Load config.yaml from project directory."""
    if config_path is None:
        config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def find_stooq_files(raw_dir: Path) -> list[Path]:
    """
    Find all .txt files in the raw stooq directory recursively.
    
    Args:
        raw_dir: Path to data/raw/stooq
        
    Returns:
        List of Path objects for .txt files.
    """
    if not raw_dir.exists():
        logger.warning(f"Stooq directory not found: {raw_dir}")
        return []
    
    files = sorted(raw_dir.glob("**/*.txt"))
    # Filter out .gitkeep
    files = [f for f in files if f.name != ".gitkeep"]
    logger.info(f"Found {len(files)} stooq files in {raw_dir}")
    return files


def parse_stooq_file(file_path: Path, sp500_universe: set[str]) -> list[PriceBar]:
    bars = []
    
    try:
        with open(file_path) as f:
            lines = f.readlines()
        
        # Skip header line
        if not lines:
            return bars
            
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            
            try:
                parts = line.split(",")
                if len(parts) < 10:
                    continue
                
                ticker_raw = parts[0].strip()
                # Remove .US suffix if present (stooq uses .US for US stocks)
                ticker = ticker_raw.replace(".US", "").replace(".us", "").upper()
                
                # FILTER: Only process S&P 500 stocks
                if ticker not in sp500_universe:
                    continue
                
                # Skip if invalid
                if not ticker:
                    continue
                
                date_str = parts[2].strip()  # YYYYMMDD
                
                # Parse date
                try:
                    bar_date = datetime.strptime(date_str, "%Y%m%d").date()
                except ValueError:
                    logger.debug(f"Invalid date: {date_str} in {file_path}")
                    continue
                
                # Parse OHLCV
                try:
                    open_price = float(parts[4])
                    high = float(parts[5])
                    low = float(parts[6])
                    close = float(parts[7])
                    volume = float(parts[8])
                except (ValueError, IndexError):
                    logger.debug(f"Invalid OHLCV data in {file_path}: {line}")
                    continue
                
                bar = PriceBar(
                    ticker=ticker,
                    date=bar_date,
                    open=open_price,
                    high=high,
                    low=low,
                    close=close,
                    volume=volume,
                    source=DataSource.STOOQ,
                )
                bars.append(bar)
                
            except Exception as e:
                logger.debug(f"Error parsing line in {file_path}: {line} → {e}")
                continue
        
        logger.debug(f"Parsed {len(bars)} bars from {file_path.name}")
        return bars
        
    except Exception as e:
        logger.error(f"Error reading file {file_path}: {e}")
        return []


def main():
    """Load all stooq files into the database (S&P 500 only)."""
    logger.info("Starting stooq data loader (S&P 500 ONLY)...")
    
    # Load S&P 500 universe
    sp500_universe = load_sp500_tickers()
    print(f"Loaded {len(sp500_universe)} S&P 500 tickers from Wikipedia")
    
    logger.info(f"Loaded {len(sp500_universe)} S&P 500 tickers")
    
    # Load config
    config = load_config()
    
    project_dir = Path(__file__).parent
    data_dir = project_dir / config.get("pipeline", {}).get("data_dir", "data")
    raw_dir = data_dir / "raw" / "stooq"
    
    logger.info(f"Stooq raw directory: {raw_dir}")
    
    # Find files
    files = find_stooq_files(raw_dir)
    if not files:
        logger.warning("No stooq files found. Exiting.")
        return
    
    # Create repository
    repo = RepositoryFactory.from_config(config)
    
    # Process all files
    total_bars = 0
    total_inserted = 0
    
    for i, file_path in enumerate(files, 1):
        #logger.info(f"[{i}/{len(files)}] Processing {file_path.name}...")
        
        bars = parse_stooq_file(file_path, sp500_universe)
        if bars:
            print(f"Parsed {len(bars)} bars from {file_path.name}")
            total_bars += len(bars)
            # Write to database in batches
            repo.write_prices(bars)
            total_inserted += len(bars)
    
    logger.info(f"✓ Loaded {total_inserted} price bars for S&P 500 stocks into database.")


if __name__ == "__main__":
    main()
