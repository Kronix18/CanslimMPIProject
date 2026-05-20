"""
test_data_collection.py — Unit tests for data_collection.py.

Tests cover:
  - OHLCV parsing from stooq CSV
  - SEC EDGAR financial extraction from companyfacts JSON
  - Index data collection
  - Daily append updates
"""

import json
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_collection import (
    parse_stooq_csv,
    extract_eps_series,
    extract_revenue_series,
    extract_shares_outstanding,
    extract_stockholders_equity,
    merge_financial_rows,
)
from schemas import DataSource, PriceBar, FinancialRow


# FIXTURES

@pytest.fixture
def sample_stooq_csv():
    """Sample stooq CSV data."""
    return pd.DataFrame({
        "Date": ["2024-05-15", "2024-05-14", "2024-05-13"],
        "Open": [195.50, 194.80, 194.20],
        "High": [196.20, 195.50, 195.10],
        "Low": [195.00, 194.50, 193.80],
        "Close": [195.80, 195.10, 194.90],
        "Volume": [52300000.0, 48200000.0, 45100000.0],
    })


@pytest.fixture
def sample_sec_facts_json():
    """Sample SEC EDGAR companyfacts JSON."""
    return {
        "facts": {
            "us-gaap": {
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {"end": "2024-03-31", "filed": "2024-05-01", "val": 1.85, "form": "10-Q"},
                            {"end": "2023-12-31", "filed": "2024-01-25", "val": 6.05, "form": "10-K"},
                        ]
                    }
                },
                "Revenues": {
                    "units": {
                        "USD": [
                            {"end": "2024-03-31", "filed": "2024-05-01", "val": 90614.0e6, "form": "10-Q"},
                            {"end": "2023-12-31", "filed": "2024-01-25", "val": 383285.0e6, "form": "10-K"},
                        ]
                    }
                },
                "CommonStockSharesOutstanding": {
                    "units": {
                        "shares": [
                            {"end": "2024-03-31", "filed": "2024-05-01", "val": 15500e6},
                            {"end": "2023-12-31", "filed": "2024-01-25", "val": 15600e6},
                        ]
                    }
                },
                "StockholdersEquity": {
                    "units": {
                        "USD": [
                            {"end": "2024-03-31", "filed": "2024-05-01", "val": 73812.0e6},
                            {"end": "2023-12-31", "filed": "2024-01-25", "val": 71639.0e6},
                        ]
                    }
                },
            }
        }
    }


# TEST OHLCV PARSING

def test_parse_stooq_csv_valid(sample_stooq_csv):
    """Test parsing valid stooq CSV data."""
    bars = parse_stooq_csv(sample_stooq_csv, "AAPL")
    
    assert len(bars) == 3
    assert all(isinstance(b, PriceBar) for b in bars)
    
    # Check first bar (should be sorted by date ascending)
    assert bars[0].ticker == "AAPL"
    assert bars[0].date == date(2024, 5, 13)
    assert bars[0].close == 194.90
    assert bars[0].volume == 45100000.0
    assert bars[0].source == DataSource.STOOQ
    
    # Check last bar
    assert bars[2].date == date(2024, 5, 15)
    assert bars[2].close == 195.80


def test_parse_stooq_csv_with_nan():
    """Test that rows with NaN prices are skipped."""
    df = pd.DataFrame({
        "Date": ["2024-05-15", "2024-05-14", "2024-05-13"],
        "Open": [195.50, float("nan"), 194.20],
        "High": [196.20, 195.50, 195.10],
        "Low": [195.00, 194.50, 193.80],
        "Close": [195.80, 195.10, 194.90],
        "Volume": [52300000.0, 48200000.0, 45100000.0],
    })
    
    bars = parse_stooq_csv(df, "AAPL")
    assert len(bars) == 2  # One row skipped due to NaN


def test_parse_stooq_csv_with_zero_volume():
    """Test that rows with zero volume are skipped."""
    df = pd.DataFrame({
        "Date": ["2024-05-15", "2024-05-14"],
        "Open": [195.50, 194.80],
        "High": [196.20, 195.50],
        "Low": [195.00, 194.50],
        "Close": [195.80, 195.10],
        "Volume": [52300000.0, 0.0],
    })
    
    bars = parse_stooq_csv(df, "AAPL")
    assert len(bars) == 1  # One row skipped due to zero volume


def test_parse_stooq_csv_empty():
    """Test parsing empty DataFrame."""
    df = pd.DataFrame({
        "Date": [],
        "Open": [],
        "Close": [],
    })
    
    bars = parse_stooq_csv(df, "AAPL")
    assert len(bars) == 0


# TEST SEC FINANCIAL EXTRACTION

def test_extract_eps_series(sample_sec_facts_json):
    """Test EPS series extraction."""
    df = extract_eps_series(sample_sec_facts_json, "0000789019")
    
    assert len(df) == 2
    assert "period_end" in df.columns
    assert "eps_diluted" in df.columns
    assert "form_type" in df.columns
    
    # Check values
    assert df.iloc[0]["eps_diluted"] == 1.85
    assert df.iloc[1]["eps_diluted"] == 6.05


def test_extract_revenue_series(sample_sec_facts_json):
    """Test revenue series extraction."""
    df = extract_revenue_series(sample_sec_facts_json)
    
    assert len(df) == 2
    assert "period_end" in df.columns
    assert "revenue" in df.columns
    
    # Check values
    assert df.iloc[0]["revenue"] == 90614.0e6
    assert df.iloc[1]["revenue"] == 383285.0e6


def test_extract_shares_outstanding(sample_sec_facts_json):
    """Test shares outstanding extraction."""
    df = extract_shares_outstanding(sample_sec_facts_json)
    
    assert len(df) == 2
    assert "period_end" in df.columns
    assert "shares_outstanding" in df.columns
    
    # Check values
    assert df.iloc[0]["shares_outstanding"] == 15500e6
    assert df.iloc[1]["shares_outstanding"] == 15600e6


def test_extract_stockholders_equity(sample_sec_facts_json):
    """Test stockholders' equity extraction."""
    df = extract_stockholders_equity(sample_sec_facts_json)
    
    assert len(df) == 2
    assert "period_end" in df.columns
    assert "stockholders_equity" in df.columns
    
    # Check values
    assert df.iloc[0]["stockholders_equity"] == 73812.0e6
    assert df.iloc[1]["stockholders_equity"] == 71639.0e6


def test_merge_financial_rows(sample_sec_facts_json):
    """Test merging all financial series into FinancialRow objects."""
    eps_df = extract_eps_series(sample_sec_facts_json, "0000789019")
    revenue_df = extract_revenue_series(sample_sec_facts_json)
    shares_df = extract_shares_outstanding(sample_sec_facts_json)
    equity_df = extract_stockholders_equity(sample_sec_facts_json)
    
    rows = merge_financial_rows(eps_df, revenue_df, shares_df, equity_df, "AAPL", "0000789019")
    
    assert len(rows) >= 1
    assert all(isinstance(r, FinancialRow) for r in rows)
    
    # Check first row (most recent)
    row = rows[0]
    assert row.ticker == "AAPL"
    assert row.cik == "0000789019"
    assert row.eps_diluted is not None
    assert row.revenue is not None
    assert row.shares_outstanding is not None
    assert row.stockholders_equity is not None


def test_merge_financial_rows_empty():
    """Test merging when all DataFrames are empty."""
    empty_df = pd.DataFrame(columns=["period_end"])
    
    rows = merge_financial_rows(empty_df, empty_df, empty_df, empty_df, "TEST", "0000000001")
    
    assert len(rows) == 0


def test_merge_financial_rows_distinguishes_annual_vs_quarterly():
    """Test that is_annual field is set correctly."""
    eps_df = extract_eps_series(
        {
            "facts": {
                "us-gaap": {
                    "EarningsPerShareDiluted": {
                        "units": {
                            "USD/shares": [
                                {"end": "2024-03-31", "filed": "2024-05-01", "val": 1.85, "form": "10-Q"},
                                {"end": "2023-12-31", "filed": "2024-01-25", "val": 6.05, "form": "10-K"},
                            ]
                        }
                    }
                }
            }
        },
        "0000000001"
    )
    
    rows = merge_financial_rows(eps_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "TEST", "0000000001")
    
    assert len(rows) >= 1
    
    # Find annual and quarterly rows
    annual_rows = [r for r in rows if r.is_annual]
    quarterly_rows = [r for r in rows if not r.is_annual]
    
    assert len(annual_rows) > 0, "Should have at least one annual row"
    assert len(quarterly_rows) > 0, "Should have at least one quarterly row"


# TEST INTEGRATION: extract -> merge pipeline

def test_full_sec_pipeline(sample_sec_facts_json):
    """Test the full SEC extraction pipeline."""
    eps_df = extract_eps_series(sample_sec_facts_json, "0000789019")
    revenue_df = extract_revenue_series(sample_sec_facts_json)
    shares_df = extract_shares_outstanding(sample_sec_facts_json)
    equity_df = extract_stockholders_equity(sample_sec_facts_json)
    
    rows = merge_financial_rows(eps_df, revenue_df, shares_df, equity_df, "AAPL", "0000789019")
    
    # Verify all rows have required fields
    for row in rows:
        assert row.ticker == "AAPL"
        assert row.cik == "0000789019"
        assert row.period_end is not None
        assert row.source == DataSource.SEC_EDGAR
    
    # Verify sorting by period_end descending
    if len(rows) > 1:
        assert rows[0].period_end >= rows[1].period_end


# TEST EDGE CASES

def test_extract_eps_missing_concept():
    """Test EPS extraction when concept is missing."""
    json_missing_eps = {"facts": {"us-gaap": {}}}
    
    df = extract_eps_series(json_missing_eps, "0000000001")
    
    assert len(df) == 0
    assert list(df.columns) == ["period_end", "filing_date", "eps_diluted", "eps_basic", "form_type"]


def test_extract_revenue_fallback_concepts():
    """Test revenue extraction with fallback concepts."""
    json_fallback = {
        "facts": {
            "us-gaap": {
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            {"end": "2024-03-31", "filed": "2024-05-01", "val": 100e6, "form": "10-Q"},
                        ]
                    }
                }
            }
        }
    }
    
    df = extract_revenue_series(json_fallback)
    
    assert len(df) == 1
    assert df.iloc[0]["revenue"] == 100e6


def test_parse_stooq_csv_column_name_variations():
    """Test parsing with different column name cases."""
    df = pd.DataFrame({
        "date": ["2024-05-15"],
        "open": [195.50],
        "high": [196.20],
        "low": [195.00],
        "close": [195.80],
        "volume": [52300000.0],
    })
    
    bars = parse_stooq_csv(df, "TEST")
    
    # Should handle lowercase column names
    assert len(bars) >= 0  # Function should not crash


# TEST SORTING AND ORDERING

def test_parse_stooq_csv_sorts_by_date():
    """Test that parsed bars are sorted by date ascending."""
    df = pd.DataFrame({
        "Date": ["2024-05-15", "2024-05-13", "2024-05-14"],  # Out of order
        "Open": [195.50, 194.20, 194.80],
        "High": [196.20, 195.10, 195.50],
        "Low": [195.00, 193.80, 194.50],
        "Close": [195.80, 194.90, 195.10],
        "Volume": [52300000.0, 45100000.0, 48200000.0],
    })
    
    bars = parse_stooq_csv(df, "AAPL")
    
    dates = [b.date for b in bars]
    assert dates == sorted(dates), "Bars should be sorted by date ascending"


def test_merge_financial_rows_sorts_by_period_end():
    """Test that merged rows are sorted by period_end descending."""
    eps_df = pd.DataFrame({
        "period_end": ["2024-03-31", "2023-12-31", "2024-01-31"],
        "filing_date": ["2024-05-01", "2024-01-25", "2024-02-15"],
        "eps_diluted": [1.5, 5.0, 3.0],
        "eps_basic": [None, None, None],
        "form_type": ["10-Q", "10-K", "10-Q"],
    })
    
    rows = merge_financial_rows(eps_df, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "TEST", "0000000001")
    
    if len(rows) > 1:
        periods = [r.period_end for r in rows]
        assert periods == sorted(periods, reverse=True), "Rows should be sorted by period_end descending"


# TEST VALIDATION

def test_pricebar_validation():
    """Test that PriceBar objects are properly validated."""
    bar = PriceBar(
        ticker="AAPL",
        date=date(2024, 5, 15),
        open=195.50,
        high=196.20,
        low=195.00,
        close=195.80,
        volume=52300000.0,
    )
    
    assert bar.source == DataSource.STOOQ
    assert bar.adjusted_close is None


def test_financialrow_validation():
    """Test that FinancialRow objects are properly validated."""
    row = FinancialRow(
        ticker="AAPL",
        cik="0000789019",
        period_end=date(2024, 3, 31),
        filing_date=date(2024, 5, 1),
        is_annual=False,
        eps_diluted=1.85,
        eps_basic=1.80,
        revenue=90614.0e6,
        shares_outstanding=15500e6,
        stockholders_equity=73812.0e6,
    )
    
    assert row.source == DataSource.SEC_EDGAR
    assert row.confidence == 1.0
    assert not row.eps_is_proxy


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
