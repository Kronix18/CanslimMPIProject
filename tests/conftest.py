"""
conftest.py — Shared pytest fixtures for the CAN SLIM pipeline test suite.

Fixtures defined here are automatically available in all test files
without explicit import (pytest discovers conftest.py automatically).

Fixture strategy:
  - Provide minimal but realistic test DataFrames (no real network calls).
  - Use tmp_path (pytest built-in) for any file-system operations.
  - Spin up an in-memory SQLite repository for integration tests.
  - All fixtures are function-scoped by default (isolated per test).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from repository import RepositoryFactory
from schemas import (
    DataSource, FactorPacket, FinancialRow, MRegime, PipelineMode,
    PriceBar, QualityFlag, UniverseRecord,
)


# CONFIG FIXTURE

@pytest.fixture
def minimal_config(tmp_path: Path) -> dict:
    """
    Return a minimal pipeline config dict suitable for unit tests.
    Uses an in-memory SQLite database.
    """
    return {
        "database": {"url": "sqlite:///:memory:"},
        "pipeline": {"mode": "BULK", "run_id": "test_run"},
        "data": {
            "raw_dir": str(tmp_path / "raw"),
            "cache_dir": str(tmp_path / "cache"),
            "processed_dir": str(tmp_path / "processed"),
        },
        "sec": {"user_agent": "TestOrg test@example.com"},
        "quality_checks": {
            "min_price_bars": 252,
            "max_filing_lag_days": 90,
            "price_gap_threshold_pct": 50.0,
        },
        "ranking": {
            "weights": {
                "C": 0.30, "A": 0.25, "N": 0.15,
                "S": 0.10, "L": 0.10, "I": 0.10,
            },
        },
    }


# REPOSITORY FIXTURE

@pytest.fixture
def in_memory_repo(minimal_config: dict):
    """
    Return an in-memory SQLite DataRepository for integration tests.
    Tables are created fresh for each test function.
    """
    return RepositoryFactory.from_config(minimal_config)


# PRICE DATA FIXTURES

@pytest.fixture
def sample_price_df() -> pd.DataFrame:
    """
    Return a 300-row synthetic OHLCV DataFrame for a single ticker.
    Prices follow a gentle upward trend with realistic noise.
    """
    # TODO: generate synthetic OHLCV data with pd.date_range
    pass


@pytest.fixture
def sample_price_bars(sample_price_df: pd.DataFrame) -> list[PriceBar]:
    """Convert sample_price_df rows to PriceBar objects."""
    # TODO: convert rows to PriceBar schema objects
    pass


@pytest.fixture
def index_price_df() -> pd.DataFrame:
    """
    Return a 300-row synthetic OHLCV DataFrame for a market index (e.g. SPY).
    Used in RS computation tests.
    """
    pass


# FINANCIAL DATA FIXTURES

@pytest.fixture
def sample_quarterly_financials() -> pd.DataFrame:
    """
    Return a 12-row DataFrame of synthetic quarterly financial data.
    EPS grows at ~30 % YoY to satisfy the C factor threshold.
    Columns: [ticker, cik, period_end, filing_date, is_annual, eps_diluted,
              eps_basic, eps_is_proxy, revenue, net_income, shares_outstanding,
              stockholders_equity, source, confidence]
    """
    pass


@pytest.fixture
def sample_annual_financials() -> pd.DataFrame:
    """
    Return a 5-row DataFrame of synthetic annual financial data.
    Annual EPS CAGR of ~30 % over 4 years.
    """
    pass


# UNIVERSE FIXTURES

@pytest.fixture
def sample_universe_records() -> list[UniverseRecord]:
    """
    Return a short list (5 records) of UniverseRecord objects.
    Used in universe and repository tests.
    """
    pass


# QUALITY FLAG FIXTURES

@pytest.fixture
def sample_quality_flag() -> QualityFlag:
    """Return a single WARNING-level QualityFlag for testing."""
    pass


# FACTOR PACKET FIXTURE

@pytest.fixture
def sample_factor_packets() -> list[FactorPacket]:
    """Return 5 synthetic FactorPacket objects with plausible scores."""
    pass
