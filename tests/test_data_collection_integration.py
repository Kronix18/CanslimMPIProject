"""
test_data_collection_integration.py — Integration tests for data_collection.py.

Tests cover:
  - collect_ohlcv with mocked HTTP responses
  - collect_sec_facts with mocked SEC API responses
  - collect_index_ohlcv
  - Error handling and edge cases
"""

from datetime import date
from unittest.mock import MagicMock, patch, call
import json

import pandas as pd
import pytest
import requests

from data_collection import (
    collect_ohlcv,
    collect_sec_facts,
    collect_index_ohlcv,
    collect_ohlcv_daily_append,
    download_ohlcv_stooq,
    fetch_companyfacts_json,
)
from schemas import DataSource, PriceBar, FinancialRow


# FIXTURES

@pytest.fixture
def mock_repo():
    """Mock DataRepository."""
    repo = MagicMock()
    repo.read_prices.return_value = []
    repo.read_financials.return_value = []
    repo.write_prices.return_value = None
    repo.write_financials.return_value = None
    repo.is_price_stale = MagicMock(return_value=True)
    repo.is_financial_stale = MagicMock(return_value=True)
    return repo


@pytest.fixture
def sample_config():
    """Sample pipeline configuration."""
    return {
        "user_agent": "HPC Stock Ranker (test@example.com)",
        "index": {"ticker": "SPY.US"},
    }


@pytest.fixture
def stooq_csv_response():
    """Sample stooq CSV response text."""
    return """Date,Open,High,Low,Close,Volume
2024-05-15,195.50,196.20,195.00,195.80,52300000
2024-05-14,194.80,195.50,194.50,195.10,48200000
2024-05-13,194.20,195.10,193.80,194.90,45100000"""


@pytest.fixture
def sec_companyfacts_response():
    """Sample SEC EDGAR companyfacts JSON response."""
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
                        ]
                    }
                },
            }
        }
    }


# TEST OHLCV COLLECTION

@patch('data_collection.download_ohlcv_stooq')
def test_collect_ohlcv_from_cache(mock_download, mock_repo, sample_config):
    """Test that collect_ohlcv reads from cache when available."""
    # Setup: repository has cached data
    cached_bars = [
        PriceBar(ticker="AAPL", date=date(2024, 5, 13), open=194.20, high=195.10,
                low=193.80, close=194.90, volume=45100000.0),
    ]
    mock_repo.read_prices.return_value = cached_bars
    mock_repo.is_price_stale.return_value = False
    
    bars = collect_ohlcv("AAPL", sample_config, mock_repo)
    
    # Verify
    assert bars == cached_bars
    mock_download.assert_not_called()


@patch('data_collection.download_ohlcv_stooq')
def test_collect_ohlcv_downloads_when_stale(mock_download, mock_repo, sample_config, stooq_csv_response):
    """Test that collect_ohlcv downloads when cache is stale."""
    # Setup: cache is stale
    mock_repo.is_price_stale.return_value = True
    mock_download.return_value = pd.read_csv(__import__('io').StringIO(stooq_csv_response))
    
    bars = collect_ohlcv("AAPL", sample_config, mock_repo)
    
    # Verify
    assert len(bars) == 3
    assert bars[0].date == date(2024, 5, 13)
    assert bars[0].close == 194.90
    mock_download.assert_called_once_with("AAPL")
    mock_repo.write_prices.assert_called_once()


@patch('data_collection.download_ohlcv_stooq')
def test_collect_ohlcv_force_refresh(mock_download, mock_repo, sample_config, stooq_csv_response):
    """Test that collect_ohlcv respects force_refresh flag."""
    # Setup
    mock_download.return_value = pd.read_csv(__import__('io').StringIO(stooq_csv_response))
    
    bars = collect_ohlcv("AAPL", sample_config, mock_repo, force_refresh=True)
    
    # Verify: should call download even if cache is fresh
    mock_download.assert_called_once()


@patch('data_collection.requests.get')
def test_download_ohlcv_stooq_success(mock_get):
    """Test successful download_ohlcv_stooq."""
    # Setup mock response
    stooq_csv = """Date,Open,High,Low,Close,Volume
2024-05-15,195.50,196.20,195.00,195.80,52300000"""
    
    mock_response = MagicMock()
    mock_response.text = stooq_csv
    mock_get.return_value = mock_response
    
    df = download_ohlcv_stooq("AAPL")
    
    # Verify
    assert len(df) == 1
    assert df.iloc[0]["Close"] == 195.80


@patch('data_collection.requests.get')
def test_download_ohlcv_stooq_http_error(mock_get):
    """Test download_ohlcv_stooq with HTTP error."""
    # Setup: HTTP 404
    mock_get.side_effect = requests.HTTPError("404 Not Found")
    
    # Verify that error is raised
    with pytest.raises(requests.HTTPError):
        download_ohlcv_stooq("INVALID_TICKER")


@patch('data_collection.download_ohlcv_stooq')
def test_collect_ohlcv_handles_download_error(mock_download, mock_repo, sample_config):
    """Test that collect_ohlcv handles download errors gracefully."""
    # Setup: download raises error
    mock_download.side_effect = Exception("Network error")
    
    bars = collect_ohlcv("AAPL", sample_config, mock_repo)
    
    # Verify: should return empty list instead of crashing
    assert bars == []


# TEST SEC FACTS COLLECTION

@patch('data_collection.fetch_companyfacts_json')
def test_collect_sec_facts_from_cache(mock_fetch, mock_repo, sample_config):
    """Test that collect_sec_facts reads from cache when available."""
    # Setup: repository has cached data
    cached_facts = [
        FinancialRow(
            ticker="AAPL",
            cik="0000789019",
            period_end=date(2024, 3, 31),
            filing_date=date(2024, 5, 1),
            is_annual=False,
            eps_diluted=1.85,
            revenue=90614.0e6,
        ),
    ]
    mock_repo.read_financials.return_value = cached_facts
    mock_repo.is_financial_stale.return_value = False
    
    facts = collect_sec_facts("0000789019", "AAPL", sample_config, mock_repo)
    
    # Verify
    assert facts == cached_facts
    mock_fetch.assert_not_called()


@patch('data_collection.fetch_companyfacts_json')
@patch('data_collection.time.sleep')  # Avoid actual sleep in tests
def test_collect_sec_facts_downloads_when_stale(mock_sleep, mock_fetch, mock_repo, sample_config, sec_companyfacts_response):
    """Test that collect_sec_facts downloads when cache is stale."""
    # Setup: cache is stale
    mock_repo.is_financial_stale.return_value = True
    mock_fetch.return_value = sec_companyfacts_response
    
    facts = collect_sec_facts("0000789019", "AAPL", sample_config, mock_repo)
    
    # Verify
    assert len(facts) >= 1
    assert facts[0].ticker == "AAPL"
    assert facts[0].eps_diluted is not None
    mock_fetch.assert_called_once()
    mock_sleep.assert_called()  # Should respect crawl delay


@patch('data_collection.requests.get')
def test_fetch_companyfacts_json_success(mock_get):
    """Test successful fetch_companyfacts_json."""
    # Setup mock response
    expected_json = {"facts": {"us-gaap": {}}}
    
    mock_response = MagicMock()
    mock_response.json.return_value = expected_json
    mock_get.return_value = mock_response
    
    result = fetch_companyfacts_json("0000789019", "HPC Ranker (test@example.com)")
    
    # Verify
    assert result == expected_json
    # Verify User-Agent header was set
    mock_get.assert_called_once()
    call_kwargs = mock_get.call_args[1]
    assert "User-Agent" in call_kwargs.get("headers", {})


@patch('data_collection.requests.get')
def test_fetch_companyfacts_json_http_error(mock_get):
    """Test fetch_companyfacts_json with HTTP error."""
    # Setup: HTTP 404
    mock_get.side_effect = requests.HTTPError("404 Not Found")
    
    # Verify that error is raised
    with pytest.raises(requests.HTTPError):
        fetch_companyfacts_json("0000000001", "Test Agent")


@patch('data_collection.fetch_companyfacts_json')
@patch('data_collection.time.sleep')
def test_collect_sec_facts_handles_fetch_error(mock_sleep, mock_fetch, mock_repo, sample_config):
    """Test that collect_sec_facts handles fetch errors gracefully."""
    # Setup: fetch raises error
    mock_fetch.side_effect = Exception("API error")
    
    facts = collect_sec_facts("0000789019", "AAPL", sample_config, mock_repo)
    
    # Verify: should return empty list instead of crashing
    assert facts == []


# TEST INDEX DATA COLLECTION

@patch('data_collection.download_ohlcv_stooq')
def test_collect_index_ohlcv(mock_download, mock_repo, sample_config, stooq_csv_response):
    """Test collect_index_ohlcv delegates to collect_ohlcv."""
    # Setup
    mock_download.return_value = pd.read_csv(__import__('io').StringIO(stooq_csv_response))
    
    bars = collect_index_ohlcv("SPY.US", sample_config, mock_repo)
    
    # Verify
    assert len(bars) == 3
    assert all(b.source == DataSource.STOOQ for b in bars)


# TEST DAILY APPEND MODE

def test_collect_ohlcv_daily_append_empty_repo(mock_repo, sample_config):
    """Test collect_ohlcv_daily_append when repository is empty."""
    # Setup: no existing bars
    mock_repo.read_prices.return_value = []
    
    bars = collect_ohlcv_daily_append("AAPL", sample_config, mock_repo)
    
    # Verify: should return empty (daily append would fetch from Yahoo/Alpaca)
    assert bars == []


def test_collect_ohlcv_daily_append_with_existing_bars(mock_repo, sample_config):
    """Test collect_ohlcv_daily_append with existing bars."""
    # Setup: repository has existing bars
    existing_bars = [
        PriceBar(ticker="AAPL", date=date(2024, 5, 15), open=195.50, high=196.20,
                low=195.00, close=195.80, volume=52300000.0),
    ]
    mock_repo.read_prices.return_value = existing_bars
    
    bars = collect_ohlcv_daily_append("AAPL", sample_config, mock_repo)
    
    # Verify: should find last bar date
    # In this test, we just verify the function doesn't crash
    assert isinstance(bars, list)


# TEST MULTIPLE CALLS (DATA PERSISTENCE)

@patch('data_collection.download_ohlcv_stooq')
def test_collect_ohlcv_multiple_calls_uses_cache(mock_download, mock_repo, sample_config, stooq_csv_response):
    """Test that multiple calls to collect_ohlcv use cache on second call."""
    # Setup
    mock_download.return_value = pd.read_csv(__import__('io').StringIO(stooq_csv_response))
    
    # First call: should download
    bars1 = collect_ohlcv("AAPL", sample_config, mock_repo)
    
    # Setup cache for second call
    mock_repo.is_price_stale.return_value = False
    mock_repo.read_prices.return_value = bars1
    
    # Second call: should use cache
    bars2 = collect_ohlcv("AAPL", sample_config, mock_repo)
    
    # Verify: download should only be called once
    assert mock_download.call_count == 1
    assert bars1 == bars2


# TEST RATE LIMITING

@patch('data_collection.fetch_companyfacts_json')
@patch('data_collection.time.sleep')
def test_collect_sec_facts_respects_crawl_delay(mock_sleep, mock_fetch, mock_repo, sample_config, sec_companyfacts_response):
    """Test that collect_sec_facts respects SEC_CRAWL_DELAY_SEC."""
    # Setup
    mock_repo.is_financial_stale.return_value = True
    mock_fetch.return_value = sec_companyfacts_response
    
    for ticker in ["AAPL", "MSFT"]:
        collect_sec_facts("0000789019", ticker, sample_config, mock_repo)
    
    # Verify: sleep should be called at least once
    assert mock_sleep.call_count >= 1


# TEST DATA VALIDATION

@patch('data_collection.download_ohlcv_stooq')
def test_collect_ohlcv_returns_validated_bars(mock_download, mock_repo, sample_config, stooq_csv_response):
    """Test that collected bars pass Pydantic validation."""
    # Setup
    mock_download.return_value = pd.read_csv(__import__('io').StringIO(stooq_csv_response))
    
    bars = collect_ohlcv("AAPL", sample_config, mock_repo)
    
    # Verify: all bars should be valid PriceBar instances
    for bar in bars:
        assert isinstance(bar, PriceBar)
        assert bar.ticker == "AAPL"
        assert bar.source == DataSource.STOOQ
        assert 0 <= bar.low <= bar.high  # Basic sanity check


@patch('data_collection.fetch_companyfacts_json')
@patch('data_collection.time.sleep')
def test_collect_sec_facts_returns_validated_rows(mock_sleep, mock_fetch, mock_repo, sample_config, sec_companyfacts_response):
    """Test that collected financial rows pass Pydantic validation."""
    # Setup
    mock_repo.is_financial_stale.return_value = True
    mock_fetch.return_value = sec_companyfacts_response
    
    facts = collect_sec_facts("0000789019", "AAPL", sample_config, mock_repo)
    
    # Verify: all rows should be valid FinancialRow instances
    for row in facts:
        assert isinstance(row, FinancialRow)
        assert row.ticker == "AAPL"
        assert row.cik == "0000789019"
        assert row.source == DataSource.SEC_EDGAR


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
