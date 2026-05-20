"""
test_integration_e2e.py — End-to-end system integration test.

Tests the complete pipeline:
1. Load universe from database
2. Load price data for a sample ticker
3. Compute all CAN SLIM factors
4. Run ranking module
5. Verify outputs are generated
"""

import tempfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest
import yaml

from data_quality import run_all_quality_checks
from financial_calcs import (
    compute_quarterly_eps_growth,
    compute_annual_eps_cagr,
    compute_roe,
)
from ranking import produce_rankings
from repository import RepositoryFactory
from schemas import (
    DataSource,
    FinancialRow,
    MRegime,
    PriceBar,
    QualityFlag,
    UniverseRecord,
)
from technical_calcs import (
    classify_price_trend,
    compute_52w_high_low,
    compute_moving_averages,
    compute_rs_score,
    compute_volume_metrics,
)


@pytest.fixture
def config():
    """Load project configuration."""
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    return cfg


@pytest.fixture
def repo(config):
    """Create repository instance."""
    return RepositoryFactory.from_config(config)


@pytest.fixture
def sample_universe(repo):
    """Load real universe from database."""
    universe = repo.read_universe()
    assert universe is not None and len(universe) > 0, "Universe table must be populated"
    return universe


@pytest.fixture
def sample_ticker(sample_universe):
    """Get a ticker that has data (AAPL)."""
    # AAPL should always be in S&P 500
    return "AAPL"


@pytest.fixture
def aapl_prices(repo, sample_ticker):
    """Load AAPL price data from database."""
    prices = repo.read_prices(sample_ticker, start_date=None, end_date=None)
    assert prices is not None and len(prices) > 0, f"No price data for {sample_ticker}"
    return prices


@pytest.fixture
def aapl_financials(repo, sample_ticker):
    """Load AAPL financial data from database."""
    # Note: database may not have financials yet, so we'll create synthetic data
    financials = repo.read_financials(sample_ticker, is_annual=None)
    
    if financials is None or len(financials) == 0:
        # Create synthetic financial data for testing
        financials = [
            FinancialRow(
                ticker=sample_ticker,
                cik="0000789019",
                period_end=date(2024, 3, 31),
                filing_date=date(2024, 5, 1),
                is_annual=False,
                eps_diluted=1.85,
                revenue=90614e6,
                shares_outstanding=15500e6,
                stockholders_equity=73812e6,
            ),
            FinancialRow(
                ticker=sample_ticker,
                cik="0000789019",
                period_end=date(2023, 12, 31),
                filing_date=date(2024, 1, 25),
                is_annual=True,
                eps_diluted=6.05,
                revenue=383285e6,
                shares_outstanding=15600e6,
                stockholders_equity=71639e6,
            ),
            FinancialRow(
                ticker=sample_ticker,
                cik="0000789019",
                period_end=date(2023, 3, 31),
                filing_date=date(2023, 5, 1),
                is_annual=False,
                eps_diluted=1.52,
                revenue=83036e6,
                shares_outstanding=15700e6,
                stockholders_equity=68800e6,
            ),
        ]
    
    return financials


# TEST: DATA LOADING

def test_universe_loaded(sample_universe):
    """Test that universe table is populated."""
    assert len(sample_universe) >= 500, "Should have 500+ S&P 500 stocks"
    # sample_universe is a DataFrame, so extract tickers
    tickers = sample_universe["ticker"].tolist() if hasattr(sample_universe, "tolist") else [u.ticker for u in sample_universe]
    assert "AAPL" in tickers, "AAPL should be in S&P 500"
    assert "MSFT" in tickers, "MSFT should be in S&P 500"


def test_price_data_exists(aapl_prices, sample_ticker):
    """Test that price data exists for sample ticker."""
    assert len(aapl_prices) > 100, f"Should have 100+ bars for {sample_ticker}"
    
    # Verify columns
    assert all(hasattr(p, "date") for p in aapl_prices)
    assert all(hasattr(p, "close") for p in aapl_prices)
    assert all(hasattr(p, "volume") for p in aapl_prices)
    
    # Verify data types
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    assert df["close"].dtype in ["float64", "float32"]
    assert df["volume"].dtype in ["float64", "float32"]


# TEST: TECHNICAL CALCULATIONS

def test_compute_moving_averages(aapl_prices):
    """Test MA computation on real data."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    mas = compute_moving_averages(df)
    
    assert "ma_10" in mas.columns
    assert "ma_20" in mas.columns
    assert "ma_200" in mas.columns
    assert len(mas) == len(df)
    
    # Most recent MA should not be NaN
    assert not pd.isna(mas.iloc[-1]["ma_200"])


def test_compute_52w_high_low(aapl_prices):
    """Test 52-week high/low computation."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    high_low = compute_52w_high_low(df)
    
    assert "high_52w" in high_low.columns
    assert "low_52w" in high_low.columns
    assert len(high_low) == len(df)
    
    # Current price should be between 52w high and low
    current_close = df.iloc[-1]["close"]
    current_high = high_low.iloc[-1]["high_52w"]
    current_low = high_low.iloc[-1]["low_52w"]
    
    assert current_low <= current_close <= current_high


def test_classify_price_trend(aapl_prices):
    """Test price trend classification."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    df = compute_moving_averages(df)
    
    trend = classify_price_trend(df)
    
    assert trend in ["UPTREND", "DOWNTREND", "SIDEWAYS"]
    # Just verify the function runs without error


def test_compute_rs_score(aapl_prices):
    """Test relative strength score computation."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    rs = compute_rs_score(df)
    
    assert isinstance(rs, float)
    assert 0 <= rs <= 100, "RS score should be 0-100"


def test_compute_volume_metrics(aapl_prices):
    """Test volume metrics computation."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    metrics = compute_volume_metrics(df)
    
    assert "vol_10_avg" in metrics.columns
    assert "vol_ratio" in metrics.columns
    assert len(metrics) == len(df)


# TEST: FINANCIAL CALCULATIONS

def test_compute_quarterly_eps_growth(aapl_financials):
    """Test quarterly EPS growth."""
    df = pd.DataFrame([f.dict() for f in aapl_financials if not f["is_annual"]])
    
    if len(df) > 1:
        growth = compute_quarterly_eps_growth(df)
        
        assert isinstance(growth, float)
        assert not pd.isna(growth)


def test_compute_annual_eps_cagr(aapl_financials):
    """Test annual EPS CAGR."""
    df = pd.DataFrame([f.dict() for f in aapl_financials if f["is_annual"]])
    
    if len(df) > 1:
        cagr = compute_annual_eps_cagr(df)
        
        assert isinstance(cagr, float)
        assert -100 < cagr < 200, "CAGR should be reasonable"


def test_compute_roe(aapl_financials):
    """Test ROE computation."""
    df = pd.DataFrame([f.dict() for f in aapl_financials if f["is_annual"]])
    
    if len(df) > 0:
        roe = compute_roe(df)
        
        assert isinstance(roe, float)
        assert 0 <= roe <= 100, "ROE should be 0-100%"


# TEST: DATA QUALITY CHECKS

def test_data_quality_checks(aapl_prices, aapl_financials, config):
    """Test data quality validation."""
    prices_df = pd.DataFrame([p.dict() for p in aapl_prices])
    financials_df = pd.DataFrame([f.dict() for f in aapl_financials])
    
    flags = run_all_quality_checks("AAPL", prices_df, financials_df, config)
    
    assert isinstance(flags, list)
    # Flags may be empty (all checks pass) or contain warnings
    assert all(isinstance(f, QualityFlag) for f in flags)


# TEST: RANKING PIPELINE

def test_produce_rankings_with_sample_data(config):
    """Test the ranking pipeline end-to-end."""
    # Create sample factor data for 10 stocks
    factor_data = {
        "ticker": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA", "META", "BRK-B", "JPM", "V"],
        "C": [85.0, 90.0, 80.0, 75.0, 95.0, 70.0, 88.0, 65.0, 82.0, 78.0],
        "A": [88.0, 85.0, 82.0, 80.0, 92.0, 72.0, 86.0, 68.0, 84.0, 80.0],
        "N": [92.0, 88.0, 85.0, 83.0, 97.0, 75.0, 90.0, 70.0, 86.0, 82.0],
        "S": [80.0, 82.0, 78.0, 76.0, 85.0, 68.0, 81.0, 62.0, 79.0, 75.0],
        "L": [90.0, 85.0, 88.0, 82.0, 95.0, 70.0, 89.0, 65.0, 84.0, 81.0],
        "I": [75.0, 80.0, 78.0, 74.0, 88.0, 65.0, 79.0, 60.0, 77.0, 72.0],
        "M": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1],  # 1 = CONFIRMED_UPTREND
    }
    df = pd.DataFrame(factor_data)
    
    # Create temporary output directory
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        
        packets = produce_rankings(
            df,
            m_regime=MRegime.CONFIRMED_UPTREND,
            config=config,
            repo=None,  # Not used for this test
            run_id="test_run_001",
            output_dir=output_dir,
        )
        
        # Verify packets are returned
        assert len(packets) > 0, "Should produce ranked packets"
        assert all(hasattr(p, "ticker") for p in packets)
        assert all(hasattr(p, "composite_score") for p in packets)
        
        # Verify output files were created
        assert (output_dir / "rankings_test_run_001.csv").exists()


def test_ranking_respects_m_gate(config):
    """Test that M-gate voids ranking when market is correcting."""
    # Create sample factor data
    factor_data = {
        "ticker": ["AAPL", "MSFT"],
        "C": [85.0, 90.0],
        "A": [88.0, 85.0],
        "N": [92.0, 88.0],
        "S": [80.0, 82.0],
        "L": [90.0, 85.0],
        "I": [75.0, 80.0],
        "M": [0, 0],
    }
    df = pd.DataFrame(factor_data)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_dir = Path(tmpdir)
        
        packets = produce_rankings(
            df,
            m_regime=MRegime.IN_CORRECTION,  # Market is correcting
            config=config,
            repo=None,
            run_id="test_correction",
            output_dir=output_dir,
        )
        
        # When market is IN_CORRECTION, M-gate should void all rankings
        # (produce_rankings should return empty)
        assert len(packets) == 0, "M-gate should void rankings when market corrects"


# TEST: INTEGRATION WITH DATABASE

def test_full_pipeline_integration(config, repo, sample_ticker):
    """Test the complete end-to-end pipeline with database."""
    # Step 1: Load universe
    universe = repo.read_universe()
    assert universe is not None
    
    # Step 2: Load price data for sample ticker
    prices = repo.read_prices(sample_ticker, start_date=None, end_date=None)
    assert prices is not None and len(prices) > 0
    
    # Step 3: Compute technical factors
    prices_df = pd.DataFrame([p.dict() for p in prices])
    prices_df = compute_moving_averages(prices_df)
    prices_df = compute_52w_high_low(prices_df)
    prices_df["rs_score"] = compute_rs_score(prices_df)
    prices_df = compute_volume_metrics(prices_df)
    
    # Step 4: Verify all factors computed without error
    required_factors = ["ma_10", "ma_20", "ma_200", "high_52w", "low_52w", "rs_score", "vol_10_avg"]
    for factor in required_factors:
        assert factor in prices_df.columns, f"Missing factor: {factor}"
    
    print(f"✓ Complete pipeline executed successfully for {sample_ticker}")


# TEST: DATA INTEGRITY

def test_no_missing_values_in_prices(aapl_prices):
    """Test that price data has no missing values."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    required_cols = ["ticker", "date", "open", "high", "low", "close", "volume"]
    for col in required_cols:
        assert col in df.columns, f"Missing column: {col}"
        assert not df[col].isna().any(), f"NaN values in {col}"


def test_price_data_consistency(aapl_prices):
    """Test that price data is internally consistent."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    # OHLC relationships
    assert (df["low"] <= df["open"]).all(), "Low should be <= Open"
    assert (df["low"] <= df["close"]).all(), "Low should be <= Close"
    assert (df["high"] >= df["open"]).all(), "High should be >= Open"
    assert (df["high"] >= df["close"]).all(), "High should be >= Close"
    assert (df["high"] >= df["low"]).all(), "High should be >= Low"
    
    # Volume should be positive
    assert (df["volume"] > 0).all(), "Volume should be positive"


# TEST: PERFORMANCE

def test_technical_calcs_performance(aapl_prices):
    """Test that calculations complete in reasonable time."""
    df = pd.DataFrame([p.dict() for p in aapl_prices])
    
    # These should all complete quickly (< 1 second for 1000+ bars)
    import time
    
    start = time.time()
    compute_moving_averages(df)
    assert time.time() - start < 1.0
    
    start = time.time()
    compute_52w_high_low(df)
    assert time.time() - start < 1.0
    
    start = time.time()
    compute_rs_score(df)
    assert time.time() - start < 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])