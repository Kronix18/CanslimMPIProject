import pandas as pd
from datetime import date, datetime
from sqlalchemy import create_engine, MetaData, Table, Column, String, Float, Date, Boolean, Integer, DateTime, text
import os

DB_PATH = "data/canslim.db"
engine = create_engine(f"sqlite:///{DB_PATH}")
metadata = MetaData()

# Table definitions
universe_table = Table("universe", metadata, Column("ticker", String(16), primary_key=True), Column("name", String(255)), Column("cik", String(10)), Column("sector", String(128)), Column("added_date", Date), Column("removed_date", Date))
price_bars_table = Table("price_bars", metadata, Column("id", Integer, primary_key=True, autoincrement=True), Column("ticker", String(16)), Column("date", Date), Column("open", Float), Column("high", Float), Column("low", Float), Column("close", Float), Column("volume", Float), Column("adjusted_close", Float), Column("source", String(32)))
financials_table = Table("financials", metadata, Column("id", Integer, primary_key=True, autoincrement=True), Column("ticker", String(16)), Column("cik", String(10)), Column("period_end", Date), Column("filing_date", Date), Column("is_annual", Boolean), Column("eps_diluted", Float), Column("eps_basic", Float), Column("eps_is_proxy", Boolean), Column("revenue", Float), Column("net_income", Float), Column("shares_outstanding", Float), Column("stockholders_equity", Float), Column("source", String(32)), Column("confidence", Float))
raw_factors_table = Table("raw_factors", metadata, Column("id", Integer, primary_key=True, autoincrement=True), Column("run_id", String(64)), Column("ticker", String(16)), Column("c_yoy_growth", Float), Column("c_score", Float), Column("a_eps_cagr", Float), Column("a_consistency", Float), Column("a_trend", Float), Column("a_score", Float), Column("n_score", Float), Column("s_score", Float), Column("l_rs_blend", Float), Column("l_percentile", Float), Column("i_score", Float), Column("m_regime", String(32)), Column("data_date", Date), Column("created_at", DateTime, default=datetime.utcnow))
rankings_table = Table("rankings", metadata, Column("id", Integer, primary_key=True, autoincrement=True), Column("run_id", String(64)), Column("ticker", String(16)), Column("final_rank", Integer), Column("c_norm", Float), Column("a_norm", Float), Column("n_norm", Float), Column("s_norm", Float), Column("l_norm", Float), Column("i_norm", Float), Column("composite_score", Float), Column("gated_score", Float), Column("m_regime", String(32)), Column("buy_signal", Boolean), Column("tiebreaker", String(128)), Column("data_date", Date), Column("created_at", DateTime, default=datetime.utcnow))

metadata.create_all(engine)

def read_universe():
    query = "SELECT * FROM universe ORDER BY ticker"
    return pd.read_sql(query, engine)

def read_prices(ticker, start_date=None, end_date=None):
    if start_date is None or end_date is None:
        query = f"SELECT * FROM price_bars WHERE ticker = :ticker ORDER BY date"
        return pd.read_sql(query, engine, params={"ticker": ticker})
    query = f"SELECT * FROM price_bars WHERE ticker = :ticker AND date BETWEEN :start AND :end ORDER BY date"
    return pd.read_sql(query, engine, params={"ticker": ticker, "start": start_date, "end": end_date})

def read_financials(ticker, is_annual=False):
    query = f"SELECT * FROM financials WHERE ticker = :ticker AND is_annual = :is_annual ORDER BY period_end"
    return pd.read_sql(query, engine, params={"ticker": ticker, "is_annual": int(is_annual)})

def clear_rankings():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM rankings"))
        conn.commit()

def clear_raw_factors():
    with engine.connect() as conn:
        conn.execute(text("DELETE FROM raw_factors"))
        conn.commit()

def get_price_dates(ticker):
    query = "SELECT DISTINCT date FROM price_bars WHERE ticker = ? ORDER BY date"
    df = pd.read_sql(query, engine, params=[ticker])
    return df["date"].tolist() if len(df) > 0 else []

def write_raw_factors(factors_list, run_id, mode="bulk"):
    df = pd.DataFrame(factors_list)
    df.insert(1, "run_id", run_id)
    df.to_sql("raw_factors", engine, if_exists="append", index=False)

def write_rankings(rankings_list, run_id, mode="bulk"):
    df = pd.DataFrame(rankings_list)
    df.insert(1, "run_id", run_id)
    df.to_sql("rankings", engine, if_exists="append", index=False)

def exec_sql(query, params=None):
    with engine.connect() as conn:
        result = conn.execute(text(query), params or {})
        conn.commit()
        rows = result.fetchall()
        cols = result.keys()
        return pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()
