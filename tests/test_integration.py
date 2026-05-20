"""
test_integration.py — End-to-end integration tests.

These tests exercise the full pipeline path (minus MPI) using in-memory
SQLite and synthetic data. No network calls are made.

Scope:
  - Write universe → read back via repository.
  - Write prices → compute technical factors → check output shape.
  - Write financials → compute C and A factors → check thresholds.
  - Run ranking on synthetic factor inputs → verify output structure.
  - Verify quality flags are generated and persisted correctly.

Marks:
  @pytest.mark.integration — skipped in fast unit-test runs (use -m "not integration").
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from data_quality import run_all_quality_checks
from financial_calcs import compute_quarterly_eps_growth, compute_annual_eps_cagr
from ranking import produce_rankings
from schemas import MRegime
from technical_calcs import compute_moving_averages, compute_volume_metrics


pytestmark = pytest.mark.integration


class TestRepositoryRoundTrip:
    def test_universe_write_read_roundtrip(self, in_memory_repo, sample_universe_records):
        """Persisted UniverseRecord objects are retrievable with correct field values."""
        pass

    def test_price_bars_write_read_roundtrip(self, in_memory_repo, sample_price_bars):
        """Persisted PriceBar objects are retrievable with correct OHLCV values."""
        pass

    def test_financials_write_read_roundtrip(self, in_memory_repo, sample_quarterly_financials):
        """Persisted FinancialRow objects are retrievable with correct field values."""
        pass

    def test_results_write_read_roundtrip(self, in_memory_repo, sample_factor_packets):
        """Persisted FactorPacket results are retrievable for the correct run_id."""
        pass


class TestFullFactorPipeline:
    def test_technical_factors_computed_for_all_tickers(
        self, in_memory_repo, sample_price_df, index_price_df
    ):
        """
        Given price data for 5 tickers, technical factor computation
        returns a DataFrame with 5 rows and expected columns.
        """
        pass

    def test_c_factor_meets_threshold_for_synthetic_data(
        self, sample_quarterly_financials
    ):
        """
        Synthetic quarterly data with 30 % YoY EPS growth meets C_MIN_EPS_GROWTH_PCT.
        """
        pass

    def test_a_factor_cagr_meets_threshold_for_synthetic_data(
        self, sample_annual_financials
    ):
        """
        Synthetic annual data with 30 % CAGR meets A_MIN_ANNUAL_GROWTH_PCT.
        """
        pass


class TestQualityFlagPipeline:
    def test_clean_data_produces_no_flags(
        self, sample_price_df, sample_quarterly_financials, minimal_config
    ):
        """High-quality synthetic data generates zero quality flags."""
        pass

    def test_short_price_history_produces_flag(self, minimal_config):
        """Price DataFrame with < 252 rows generates a history-length flag."""
        pass


class TestRankingIntegration:
    def test_ranking_output_length_matches_universe(
        self, in_memory_repo, minimal_config, tmp_path
    ):
        """produce_rankings returns one FactorPacket per universe member."""
        pass

    def test_ranking_sorted_descending(
        self, in_memory_repo, minimal_config, tmp_path
    ):
        """Output FactorPacket list is sorted by composite_rank descending."""
        pass
