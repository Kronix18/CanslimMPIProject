import pandas as pd
import numpy as np
from datetime import date

def compute_c_factor(fin_q):
    # Quarterly EPS growth (>=25%) YOY
    if fin_q is None or fin_q.empty or len(fin_q) < 4:
        return None, 0
    
    latest_eps = fin_q.iloc[-1]["eps_diluted"]
    prior_eps = fin_q.iloc[-5]["eps_diluted"] # same quarter one year earlier
    
    # Handle None and NaN
    if pd.isna(latest_eps) or pd.isna(prior_eps) or prior_eps == 0:
        return None, 0
    
    growth = ((latest_eps - prior_eps) / abs(prior_eps)) * 100
    score = 1 if growth >= 25 else 0
    return growth, score

def compute_a_factor(fin_a):
    # 3-year EPS CAGR (>=25%)
    if fin_a is None or fin_a.empty or len(fin_a) < 3:
        return None, 0, 0, 0
    
    latest_eps = fin_a.iloc[-1]["eps_diluted"]
    oldest_eps = fin_a.iloc[max(0, len(fin_a)-3)]["eps_diluted"]
    
    # Handle None and NaN
    if pd.isna(latest_eps) or pd.isna(oldest_eps) or oldest_eps <= 0:
        return None, 0, 0, 0
    
    # Ensure positive ratio before taking power
    ratio = latest_eps / oldest_eps
    if ratio <= 0:
        return None, 0, 0, 0
    
    cagr = (ratio ** (1/3) - 1) * 100
    trend = 1 if cagr > 0 else 0
    score = 1 if cagr >= 25 else 0
    
    return cagr, 1, trend, score

def compute_nsl_factors(prices):
    # Technical factors: N (YoY price change %), S, L (simplified)
    if prices is None or prices.empty or len(prices) < 252:
        return 0, 0, None, "Market in Correction"
    
    close_latest = prices["close"].iloc[-1]
    close_1y_ago = prices["close"].iloc[-252]
    
    # Handle NaN values
    if pd.isna(close_latest) or pd.isna(close_1y_ago):
        n_yoy_change = 0
    else:
        n_yoy_change = ((close_latest - close_1y_ago) / close_1y_ago * 100) if close_1y_ago > 0 else 0
    
    # S: Volume trend
    # volume average is positive
    vol_sma_50 = prices["volume"].rolling(window=50, min_periods=1).mean().iloc[-1]
    s_score = vol_sma_50
    
    # L: Relative strength (20-day momentum)
    close_20d_ago = prices["close"].iloc[-20]
    if pd.isna(close_latest) or pd.isna(close_20d_ago) or close_20d_ago <= 0:
        l_rs = None
    else:
        l_rs = (close_latest / close_20d_ago - 1) * 100
    
    return n_yoy_change, s_score, l_rs, "Confirmed Uptrend"

def compute_factors_for_ticker(db, ticker, data_date):
    factors = {
        "ticker": ticker, "data_date": data_date,
        "c_yoy_growth": None, "c_score": 0,
        "a_eps_cagr": None, "a_consistency": 0, "a_trend": 0, "a_score": 0,
        "n_score": 0, "s_score": 0,
        "l_rs_blend": None, "l_percentile": 0,
        "i_score": 0, "m_regime": "Market in Correction",
    }
    
    try:
        fin_q = db.read_financials(ticker, is_annual=False)
        c_growth, c_score = compute_c_factor(fin_q)
        factors["c_yoy_growth"] = c_growth
        factors["c_score"] = c_growth
        
        fin_a = db.read_financials(ticker, is_annual=True)
        a_cagr, a_cons, a_trend, a_score = compute_a_factor(fin_a)
        factors["a_eps_cagr"] = a_cagr
        factors["a_consistency"] = a_cons
        factors["a_trend"] = a_trend
        factors["a_score"] = a_score
        
        prices = db.read_prices(ticker)
        n_score, s_score, l_rs, m_regime = compute_nsl_factors(prices)
        factors["n_score"] = n_score
        factors["s_score"] = s_score
        factors["l_rs_blend"] = l_rs
        factors["m_regime"] = m_regime
        
        return factors
    except:
        return None


def finalize_rankings(db, all_factors, m_regime):
    if not all_factors:
        return []
    
    df = pd.DataFrame(all_factors)
    
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
    df["composite_score"] = df[available_cols].mean(axis=1)
    
    # M-gate: apply market regime filter
    df["gated_score"] = np.where(df["m_regime"] == "Confirmed Uptrend", df["composite_score"], df["composite_score"] * 0.5)
    df["buy_signal"] = df["gated_score"] > 50
    
    # Rank from 99 (best) to 1 (worst) within each date using percentile
    df["final_rank"] = (df.groupby("data_date")["composite_score"].rank(pct=True) * 98 + 1).astype(int)
    
    # Return required columns with normalized raw factors
    rankings = df[[
        "ticker", "final_rank", "c_yoy_growth_norm", "a_eps_cagr_norm", "n_score_norm",
        "s_score_norm", "l_percentile", "composite_score", "gated_score", "m_regime",
        "buy_signal", "data_date"
    ]].rename(columns={
        "c_yoy_growth_norm": "c_norm", "a_eps_cagr_norm": "a_norm", "n_score_norm": "n_norm",
        "s_score_norm": "s_norm", "l_percentile": "l_norm"
    }).assign(i_norm=0, tiebreaker="").to_dict('records')
    
    return rankings
