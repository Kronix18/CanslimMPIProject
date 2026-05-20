#!/usr/bin/env python3
"""
test_validation.py — Quick smoke test of core functionality.

Run with:
    python test_validation.py
"""

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from repository import RepositoryFactory
from schemas import PriceBar, DataSource, FinancialRow
from technical_calcs import (
    compute_moving_averages,
    compute_52w_high_low,
    classify_price_trend,
    compute_market_index_series,
    classify_m_regime,
)
from financial_calcs import (
    compute_quarterly_eps_growth,
    compute_annual_eps_cagr,
    compute_shares_trend,
)
from data_quality import (
    check_price_history_length,
    check_financial_row_count,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_repository():
    """Test that repository can load stooq price data."""
    logger.info("Testing repository...")
    
    config = {"database": {"url": "sqlite:///data/canslim.db"}}
    repo = RepositoryFactory.from_config(config)
    
    # Try to load a known ticker
    prices = repo.read_prices("AAPL", date(2020, 1, 1), date(2020, 12, 31))
    
    assert not prices.empty, "No price data found for AAPL"
    assert len(prices) > 200, f"Expected ~250 trading days, got {len(prices)}"
    
    logger.info(f"✓ Repository: loaded {len(prices)} AAPL bars")
    return prices


def test_technical_calcs(prices: pd.DataFrame):
    """Test technical analysis calculations."""
    logger.info("Testing technical calculations...")
    
    # Moving averages
    df = compute_moving_averages(prices)
    assert "ma21" in df.columns
    assert "ma200" in df.columns
    assert not df["ma200"].iloc[-1] is None  # Latest MA200 should have value
    logger.info(f"✓ Moving averages computed (MA200={df['ma200'].iloc[-1]:.2f})")
    
    # 52-week highs
    df = compute_52w_high_low(df)
    assert "w52_high" in df.columns
    assert "w52_high_pct" in df.columns
    logger.info(f"✓ 52W high computed (price/52W high={df['w52_high_pct'].iloc[-1]:.2%})")
    
    # Price trend
    trend = classify_price_trend(df)
    assert len(trend) == len(df)
    latest_trend = trend.iloc[-1]
    logger.info(f"✓ Price trend: {latest_trend}")


def test_financial_calcs():
    """Test financial calculations."""
    logger.info("Testing financial calculations...")
    
    # Create mock financial data
    financials = pd.DataFrame({
        "period_end": [
            date(2017, 12, 31), date(2018, 12, 31), date(2019, 12, 31),
            date(2020, 12, 31), date(2021, 12, 31), date(2022, 12, 31),
        ],
        "is_annual": [True] * 6,
        "eps_diluted": [2.97, 2.97, 5.61, 3.28, 5.61, 5.94],
        "shares_outstanding": [4.6e9] * 6,
    })
    
    # CAGR
    cagr = compute_annual_eps_cagr(financials, years=3)
    assert not pd.isna(cagr)
    assert cagr > 0, "Expected positive EPS CAGR"
    logger.info(f"✓ Annual EPS CAGR: {cagr:.2%} over 3 years")
    
    # Shares trend
    shares_change = compute_shares_trend(financials, lookback_quarters=4)
    assert pd.notna(shares_change)
    logger.info(f"✓ Shares outstanding change: {shares_change:.1f}%")


def test_data_quality():
    logger.info("Testing data quality checks...")
    
    # Create test data
    prices = pd.DataFrame({
        "date": pd.date_range("2020-01-01", periods=260),
        "open": [100.0] * 260,
        "high": [100.5] * 260,
        "low": [99.5] * 260,
        "close": [100.0] * 260,
        "volume": [1e6] * 260,
    })
    
    # Check price history
    flag = check_price_history_length("TEST", prices, min_bars=252)
    assert flag is None, "Should pass with 260 bars (1 year+)"
    logger.info("✓ Price history check: PASS")
    
    # Check financial row count
    financials = pd.DataFrame({
        "period_end": pd.date_range("2020-01-01", periods=8, freq="QE"),
        "is_annual": [False] * 8,
        "eps_diluted": [1.0] * 8,
    })
    flags = check_financial_row_count("TEST", financials, min_quarterly=5, min_annual=0)
    assert len(flags) == 0, f"Should pass with 8 quarters, got {flags}"
    logger.info("✓ Financial row count check: PASS")


def main():
    """Run all validation tests."""
    logger.info("=" * 60)
    logger.info("CAN SLIM HPC Project — Validation Test Suite")
    logger.info("=" * 60)
    
    try:
        # Repository test
        prices = test_repository()
        
        # Technical calculations
        test_technical_calcs(prices)
        
        # Financial calculations
        test_financial_calcs()
        
        # Data quality
        test_data_quality()
        
        logger.info("=" * 60)
        logger.info("✓ ALL TESTS PASSED")
        logger.info("=" * 60)
        return 0
        
    except Exception as e:
        logger.exception(f"✗ TEST FAILED: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
