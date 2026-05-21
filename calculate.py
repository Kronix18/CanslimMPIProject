import pandas as pd
import numpy as np
from datetime import date

def compute_c_factor_vectorized(fin_q):
    """
    Compute quarterly YoY EPS growth vectorized for all available quarters.
    fin_q: DataFrame of quarterly financials sorted by date
    Returns: Series with c_yoy_growth indexed by date, or empty if insufficient data
    """
    if fin_q is None or fin_q.empty or len(fin_q) < 8:  # Need at least 4 quarters x2 for YoY
        return pd.Series(dtype=float)
    
    # For each quarter, compare to same quarter 1 year ago (4 quarters back)
    results = {}
    for idx in range(4, len(fin_q)):
        latest_eps = fin_q.iloc[idx]["eps_diluted"]
        prior_eps = fin_q.iloc[idx - 4]["eps_diluted"]
        
        if pd.isna(latest_eps) or pd.isna(prior_eps) or prior_eps == 0:
            growth = 0
        else:
            growth = ((latest_eps - prior_eps) / abs(prior_eps)) * 100
        
        # Use the date of the latest quarter
        date_key = fin_q.iloc[idx].get("period_end", idx)
        results[date_key] = growth
    
    return pd.Series(results)


def compute_a_factor_vectorized(fin_a):
    """
    Compute 3-year EPS CAGR vectorized for all available years.
    fin_a: DataFrame of annual financials sorted by date
    Returns: Series with a_eps_cagr indexed by date, or empty if insufficient data
    """
    if fin_a is None or fin_a.empty or len(fin_a) < 3:
        return pd.Series(dtype=float)
    
    # For each year starting from year 3, compute 3-year CAGR
    results = {}
    for idx in range(2, len(fin_a)):
        latest_eps = fin_a.iloc[idx]["eps_diluted"]
        oldest_eps = fin_a.iloc[idx - 2]["eps_diluted"]  # 3-year span
        
        if pd.isna(latest_eps) or pd.isna(oldest_eps) or oldest_eps <= 0:
            cagr = 0
        else:
            ratio = latest_eps / oldest_eps
            if ratio <= 0:
                cagr = 0
            else:
                cagr = (ratio ** (1/3) - 1) * 100
        
        date_key = fin_a.iloc[idx].get("period_end", idx)
        results[date_key] = cagr
    
    return pd.Series(results)

def compute_nsl_factors_vectorized(prices_df, days):
    """
    Compute N, S, L factors vectorized for the entire price dataframe.
    Requires 252+ days for full calculation (1 year for N factor).
    prices_df: DataFrame with columns [date, close, volume] sorted by date
    days: Number of recent days to return results for
    Returns: DataFrame with columns [date, n_score, s_score, l_rs_blend] for last `days` rows
    """
    if prices_df is None or prices_df.empty or len(prices_df) < 272:  # 252 + 20 for L factor
        return pd.DataFrame(columns=["date", "n_score", "s_score", "l_rs_blend"])
    
    df = prices_df.copy()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
    
    # N: YoY price change % (requires 252 days of data)
    df["n_score"] = np.where(
        df.index >= 252,
        (df["close"] - df["close"].shift(252)) / df["close"].shift(252) * 100,
        0
    )
    
    # S: Volume trend (50-day avg vs 50-100 day avg)
    vol_recent = df["volume"].rolling(window=50, min_periods=1).mean()
    vol_prior = df["volume"].rolling(window=50, min_periods=1).mean().shift(50)
    df["s_score"] = np.where(vol_recent > vol_prior.fillna(0), 1, 0)
    
    # L: 20-day momentum % (requires 20 days of data)
    df["l_rs_blend"] = np.where(
        df.index >= 20,
        (df["close"] / df["close"].shift(20) - 1) * 100,
        0
    )
    
    # Return only the last `days` rows with valid data (index >= 252)
    valid_data = df[df.index >= 252].tail(days)[["date", "n_score", "s_score", "l_rs_blend"]].copy()
    
    return valid_data.reset_index(drop=True)

def compute_factors_for_ticker(db, ticker, days):
    """
    Compute CANSLIM factors for a ticker vectorized across multiple dates.
    db: Database object
    ticker: Stock ticker symbol
    days: Number of trading days to compute for (function internally fetches days+252 price data for lookback)
    Returns: DataFrame with columns [ticker, data_date, c_yoy_growth, a_eps_cagr, n_score, s_score, l_rs_blend, i_score, m_regime]
    """
    try:
        # Load price data: need days + 252 for 1-year lookback
        prices = db.read_prices(ticker)
        if prices is None or prices.empty or len(prices) < 252 + days:
            return pd.DataFrame()
        
        # Load financials: all available (will filter later)
        fin_q = db.read_financials(ticker, is_annual=False)
        fin_a = db.read_financials(ticker, is_annual=True)
        
        # Compute N, S, L factors vectorized with buffer to ensure valid lookback
        # Pass days + 252 to get enough history for N factor lookback, then filter to last `days` at the end
        nsl_df = compute_nsl_factors_vectorized(prices, days + 252)
        if nsl_df.empty:
            return pd.DataFrame()
        
        # Compute C factor vectorized (returns series indexed by period_end date)
        c_series = compute_c_factor_vectorized(fin_q)
        
        # Compute A factor vectorized (returns series indexed by period_end date)
        a_series = compute_a_factor_vectorized(fin_a)
        
        # Create result dataframe from NSL data
        result_df = nsl_df.copy()
        result_df["ticker"] = ticker
        
        # Fill C and A factors using forward fill (use most recent available values)
        # For each row, use the most recent C and A value available
        result_df["c_yoy_growth"] = 0
        result_df["a_eps_cagr"] = 0
        
        if not c_series.empty:
            result_df["c_yoy_growth"] = c_series.iloc[-1] if len(c_series) > 0 else 0
        
        if not a_series.empty:
            result_df["a_eps_cagr"] = a_series.iloc[-1] if len(a_series) > 0 else 0
        
        result_df["i_score"] = 0  # Not implemented
        result_df["m_regime"] = "Confirmed Uptrend"  # Placeholder
        result_df.rename(columns={"date": "data_date"}, inplace=True)
        
        # Filter to return only the last `days` rows (not the full buffer)
        if len(result_df) > days:
            result_df = result_df.iloc[-days:].reset_index(drop=True)
        
        # Return with required columns in order
        return result_df[["ticker", "data_date", "c_yoy_growth", "a_eps_cagr", "n_score", "s_score", "l_rs_blend", "i_score", "m_regime"]]
    
    except Exception as e:
        print(f"Error computing factors for {ticker}: {e}")
        return pd.DataFrame()


def finalize_rankings(db, all_factors, m_regime):
    # Handle different input types: DataFrame, list of DataFrames, or list of dicts
    if isinstance(all_factors, pd.DataFrame):
        df = all_factors
    elif isinstance(all_factors, list):
        if not all_factors:
            return []
        # Check if it's a list of DataFrames (from multiple workers)
        if isinstance(all_factors[0], pd.DataFrame):
            df = pd.concat(all_factors, ignore_index=True)
        else:
            # List of dictionaries
            df = pd.DataFrame(all_factors)
    else:
        return []
    
    if df.empty:
        return []
    
    # Normalize RAW values (not scores) to 0-100 for each date
    raw_cols = ["c_yoy_growth", "a_eps_cagr", "n_score", "l_rs_blend"]
    
    for col in raw_cols:
        if col not in df.columns:
            df[col] = 0


    
    # Group by date for normalization within each date
    for date_val in df["data_date"].unique():
        mask = df["data_date"] == date_val
        for col in raw_cols:
            date_data = df.loc[mask, col]
            minv = date_data.min()
            maxv = date_data.max()
            
            if (maxv - minv) > 0:
                df.loc[mask, f"{col}_norm"] = (df.loc[mask, col] - minv) / (maxv - minv) * 100
            else:
                df.loc[mask, f"{col}_norm"] = 50  # Default to mid-range if all same
    
    # S score (binary 0/1)
    if "s_score" in df.columns:
        df["s_score_norm"] = df.groupby("data_date")["s_score"].rank(pct=True) * 98 + 1
    else:
        df["s_score_norm"] = 1
    # L percentile (already 0-100)
    if "l_rs_blend" in df.columns:
        df["l_percentile"] = df.groupby("data_date")["l_rs_blend"].rank(pct=True) * 98 + 1
    else:
        df["l_percentile"] = 1
    
    # Composite score from normalized raw values
    norm_cols = ["c_yoy_growth_norm", "a_eps_cagr_norm", "n_score_norm", "s_score_norm", "l_percentile"]
    available_cols = [col for col in norm_cols if col in df.columns]
    
    if available_cols:
        df["composite_score"] = df[available_cols].mean(axis=1, skipna=True)
    else:
        df["composite_score"] = 50  # Default if no normalized columns available
    
    # Fill any NaN values
    df["composite_score"] = df["composite_score"].fillna(50)
    
    # M-gate: apply market regime filter
    df["gated_score"] = np.where(df["m_regime"] == "Confirmed Uptrend", df["composite_score"], df["composite_score"] * 0.5)
    df["buy_signal"] = df["gated_score"] > 50
    
    # Rank from 99 (best) to 1 (worst) within each date using percentile
    df["final_rank"] = (df.groupby("data_date")["composite_score"].rank(pct=True) * 98 + 1).astype(int)
    
    # Return required columns with normalized raw factors
    # Only select columns that actually exist in the dataframe
    required_cols = [
        "ticker", "final_rank", "c_yoy_growth_norm", "a_eps_cagr_norm", "n_score_norm",
        "s_score_norm", "l_percentile", "composite_score", "gated_score", "m_regime",
        "buy_signal", "data_date"
    ]
    cols_to_use = [col for col in required_cols if col in df.columns]
    
    if not cols_to_use:
        return []
    
    rankings = df[cols_to_use].rename(columns={
        "c_yoy_growth_norm": "c_norm", "a_eps_cagr_norm": "a_norm", "n_score_norm": "n_norm",
        "s_score_norm": "s_norm", "l_percentile": "l_norm"
    }).assign(i_norm=0, tiebreaker="").to_dict('records')
    
    return rankings
