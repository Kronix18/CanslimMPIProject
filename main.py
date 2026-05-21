#!/usr/bin/env python3

import argparse, sys, uuid
from pathlib import Path
from datetime import date
import yaml
import pandas as pd
from mpi4py import MPI
import yfinance as yf

from logging_config import get_rank_logger
import db
from calculate import compute_factors_for_ticker, finalize_rankings

COMM = MPI.COMM_WORLD
RANK = COMM.Get_rank()
SIZE = COMM.Get_size()
logger = get_rank_logger(__name__)


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        config = yaml.safe_load(f)
    for key in ["pipeline", "database"]:
        if key not in config:
            raise ValueError(f"Missing: {key}")
    return config


def compute_ticker_factors(ticker, days):
    """Compute all factors for a ticker across dates."""
    factors = []
    f = compute_factors_for_ticker(db, ticker, days)
    if isinstance(f, pd.DataFrame) and not f.empty:
        factors.append(f)
    return factors


def run_bulk(config, days = 0):
    """Run bulk factor computation and ranking."""
    
    # Get dates and tickers
    if days <= 0:
        logger.warning(f"Defaulting to INT LIMIT for days since non-positive value provided: {days}")
        days = int(1e9)
    
    
    universe = db.read_universe()
    tickers = universe["ticker"].tolist() if universe is not None else []
    
    if SIZE < 2:
        # Single process: compute all, write raw factors, calculate rankings
        db.clear_rankings()
        db.clear_raw_factors()
        
        all_factors = []
        for ticker in tickers:
            factors = compute_ticker_factors(ticker, days)  # Pass raw days; function handles lookback internally
            all_factors.extend(factors)
            db.write_raw_factors(factors, str(uuid.uuid4()), mode="bulk")
            # Log actual number of factors (rows), not DataFrames
            factors_count = len(factors[0]) if factors and isinstance(factors[0], pd.DataFrame) else 0
            logger.info(f"Computed {factors_count} factors for {ticker}")
        
        rankings = finalize_rankings(None, all_factors, "Confirmed Uptrend")
        db.write_rankings(rankings, str(uuid.uuid4()), mode="bulk")
        # Calculate total factors from all DataFrames
        total_factors = sum(len(f) if isinstance(f, pd.DataFrame) else 0 for f in all_factors)
        logger.info(f"Bulk complete: {total_factors} factors, {len(rankings)} rankings")
    
    else:
        # Multi-process: orchestrator distributes work, workers compute
        if RANK == 0:
            
            #db.clear_rankings()
            #db.clear_raw_factors()
            
            # Send tickers to workers round-robin
            worker_ranks = list(range(1, SIZE))
            
            for i, ticker in enumerate(tickers):
                worker = worker_ranks[i % len(worker_ranks)]
                COMM.send({"ticker": ticker, "days": days}, dest=worker)
                logger.info(f"Sent {ticker} to worker {worker}")
            
            # Send stop signal to all workers
            for worker in worker_ranks:
                COMM.send({"ticker": None}, dest=worker)
                # logger.info(f"Sent stop signal to worker {worker}")
            
            logger.info(f"Sent {len(tickers)} tickers to {len(worker_ranks)} workers")
            
            # Collect all results
            all_factors = []
            for _ in range(len(tickers)):
                factors = COMM.recv(source=MPI.ANY_SOURCE)
                # Handle both DataFrame and dict list responses
                if isinstance(factors, pd.DataFrame):
                    if not factors.empty:
                        total_factors = sum(len(f) if isinstance(f, pd.DataFrame) else 0 for f in [factors])
                        logger.info(f"Received factors from worker: {total_factors} factors")
                        all_factors.append(factors)
                elif isinstance(factors, list):
                    if factors:
                        total_factors = sum(len(f) if isinstance(f, pd.DataFrame) else 0 for f in factors)
                        logger.info(f"Received factors from worker: {total_factors} factors")
                        all_factors.extend(factors)
            
            # Write raw factors
            if all_factors:
                db.write_raw_factors(all_factors, str(uuid.uuid4()), mode="bulk")
            
            # Calculate and write rankings
            rankings = finalize_rankings(None, all_factors, "Confirmed Uptrend")
            db.write_rankings(rankings, str(uuid.uuid4()), mode="bulk")
            # Calculate total factors from all DataFrames
            total_factors = sum(len(f) if isinstance(f, pd.DataFrame) else 0 for f in all_factors)
            logger.info(f"Orchestrator: {total_factors} factors -> {len(rankings)} rankings")
        
        else:
            # Worker: receive tickers, compute, send results (NO DB writes)
            while True:
                msg = COMM.recv(source=0)
                ticker = msg.get("ticker")
                
                if ticker is None:
                    break
                
                factors = compute_ticker_factors(ticker, msg["days"])  # Function handles 252-day buffer internally
                COMM.send(factors, dest=0)
                # Log actual number of factors (rows), not DataFrames
                factors_count = len(factors[0]) if factors and isinstance(factors[0], pd.DataFrame) else 0
                logger.info(f"Worker {RANK}: {ticker} -> {factors_count} factors")

def main():
    parser = argparse.ArgumentParser(description="HPC CAN SLIM Pipeline")
    parser.add_argument("--config", type=Path, default="config.yaml")
    parser.add_argument("--mode", choices=["bulk", "daily"], default="bulk")
    parser.add_argument("--days", type=int, default=1, help="Number of recent days to process (bulk mode)")
    parser.add_argument("--tickers", nargs="+")
    args = parser.parse_args()
    
    if RANK == 0:
        logger.info(f"MPI {SIZE} ranks - mode {args.mode}")
    
    try:
        config = load_config(args.config)
        config = COMM.bcast(config, root=0)
        
        if args.mode == "daily":
            logger.info("Running daily mode")

        run_bulk(config, args.days if args.mode == "bulk" else None)
        
        if RANK == 0:
            logger.info("Pipeline complete")
    
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)

def fetch_daily_yahoo_prices():
    """Fetch daily price data for a ticker from Yahoo Finance."""
    tickers = db.read_universe()["ticker"].tolist()
    if not tickers:
        logger.warning("Universe is empty, cannot fetch prices")
        return 0
    try:
        data = yf.download(tickers, period="1d", group_by='ticker', threads=True)
        bars = []
        for ticker in tickers:
            try:
                df = data[ticker]
                if df.empty:
                    logger.debug(f"No data for {ticker}")
                    continue
                row = df.iloc[0]
                bar = PriceBar(
                    ticker=ticker,
                    date=row.name.date(),
                    open=row['Open'],
                    high=row['High'],
                    low=row['Low'],
                    close=row['Close'],
                    volume=int(row['Volume']),
                    source=DataSource.YAHOO
                )
                bars.append(bar)
            except Exception as e:
                logger.debug(f"Error processing data for {ticker}: {e}")
                continue
        logger.info(f"Fetched daily prices for {len(bars)} tickers from Yahoo Finance")
    except Exception as e:
        logger.error(f"Error fetching daily prices from Yahoo Finance: {e}")
        return 0

    try:
        db.save_price_bars(bars)
        logger.info(f"Saved {len(bars)} price bars to database")
    except Exception as e:
        logger.error(f"Error saving price bars to database: {e}")
        return 0
    return len(bars)

def fetch_sec_financials():
    pass

if __name__ == "__main__":
    main()
