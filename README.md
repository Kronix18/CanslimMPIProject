# HPC CANSLIM Stock Ranking Pipeline

This is a distributed stock ranking system that evaluates 503+ stocks daily using CANSLIM factors (a popular stock selection methodology). It ranks them on a scale of 99 (best) to 1 (worst) based on earnings growth, price momentum, volume, and other fundamentals.

## Quick Start

First, set up your environment:

```bash
cd /tank/data/RSS/HPC/project
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Download daily stock data from stooq.com. You'll need:
1. Daily price data (OHLCV) for all 503 stocks
2. Unzip into `data/raw/stooq/` directory

The system will automatically load the data into SQLite on first run. The database file (`data/canslim.db`) is not included in the repository because it's too large, so you must provide the raw data.

Then run one of these:

```bash
# Rank all stocks (single process, takes 15-20 minutes)
python3 main.py --mode bulk

# Faster with multiple cores (4 processes, takes 5-10 minutes)
mpirun -np 4 python3 main.py --mode bulk

# Just update a few stocks for today
python3 main.py --mode daily --tickers AAPL MSFT TSLA
```

Your results go into `data/canslim.db`:
- Rankings table contains the final scores and ranks
- Raw factors table contains the underlying calculations

## Understanding the Results

The output gives each stock a rank from 99 down to 1 for each trading day. Here's what you're looking at:

**Rank Scale:**
- 99 = Best performing stock that day
- 50 = Middle of the pack
- 1 = Worst performing stock

**Composite Score (also 1-99):** This is the average of five factors, each measuring something different about the stock:

- **C Factor**: How much the company's quarterly earnings grew compared to last year
- **A Factor**: The long-term earnings growth rate over the past 3 years
- **N Factor**: How much the stock price has gone up in the past year
- **S Factor**: Whether the stock is trading on higher volume than usual (sign of institutional interest)
- **L Factor**: Short-term price momentum over the past 20 days

The system also checks if the overall market is in an "uptrend" before giving a buy signal, but that's currently just a placeholder in the code.

## How It Works

The system is built for speed using MPI (Message Passing Interface), which lets it spread the work across multiple computer cores. Here's the basic flow:

1. Rank 0 (the main process) loads all 503 stock tickers and the full price/earnings history
2. It sends each ticker to a worker process
3. Worker processes calculate the five CANSLIM factors for each stock across 252 trading days
4. Rank 0 collects all the results, scores them, and writes everything to the database

The database has these tables:
- `universe`: Your 503 stocks with basic info (created from config)
- `price_bars`: Daily prices from stooq downloads
- `financials`: Quarterly and annual earnings data from SEC filings
- `raw_factors`: The calculated C, A, N, S, L scores for each stock-date
- `rankings`: The final 99-1 rankings with composite scores

## Performance & Scalability

Runtime scales with process count, but SQLite becomes the bottleneck beyond 8 processes. Results below are measured averages across 3 runs (503 stocks × 50 trading days):

| Processes | Measured Time | Speedup | Efficiency |
|-----------|---------------|---------|-----------|
| 1 | 152s | 1.0x | 100% |
| 2 | 206s ⚠ | 0.7x | 37% |
| 4 | 79s | 1.9x | 48% |
| 6 | 53s | 2.8x | 47% |
| 8 | 41s | 3.7x | 46% |
| 12 | 33s | 4.6x | 38% |

⚠ 2-process run is slower than 1-process. With only 1 active worker, MPI orchestration overhead (process launch, serialization, blocking send/recv) exceeds the computation saved.

Processing 503 tickers × 252 days = 127,000 factor calculations per run.

### Benchmarking

Run full performance analysis with 3 iterations per process count:

```bash
./run_benchmarks.sh              # Forward: 1, 2, 4, 6, 8, 12
./run_benchmarks.sh --reverse    # Reverse: 12, 8, 6, 4, 2, 1
cat BENCHMARK_RESULTS.txt        # View speedup and Karp-Flatt metrics
```

For detailed analysis of scaling behavior, bottleneck identification (MPI communication, SQLite writes, load imbalance), and interpretation of metrics, see [PERFORMANCE_ANALYSIS.md](PERFORMANCE_ANALYSIS.md).

**Sweet Spot**: 4–8 processes (46–48% efficiency, 1.9–3.7x speedup). Adding more processes beyond 8 yields diminishing returns due to SQLite write bottleneck on Rank 0.

**Optimization Path**: Switch to PostgreSQL for true parallel writes and linear scaling beyond 8 processes.

## Configuration

Edit `config.yaml` to customize:
- `pipeline.name`: Project identifier (for logging)
- `pipeline.year`: Historical lookback window
- `database.path`: Location of SQLite database (default: `data/canslim.db`)

Most users don't need to change anything here.

## Example: Get Today's Top 10

```sql
SELECT ticker, final_rank, composite_score, c_norm, a_norm, n_norm, s_norm, l_norm
FROM rankings
WHERE data_date = DATE('now')
ORDER BY final_rank DESC
LIMIT 10;
```

## Current Limitations

Understand these before relying on the rankings:

- **I Factor (Institutional Ownership)**: Not implemented—always scores 0. Need SEC Form 13F data to add this.
- **M Factor (Market Regime)**: Hardcoded to "Confirmed Uptrend". Real implementation would need to check SPY/QQQ vs 200-day MA.
- **Incomplete Price History**: Stocks without 252 days of price data score lower or are excluded.
- **Earnings Gaps**: Missing quarterly data gets scored as 0, not interpolated.
- **No Adjustments**: Stock splits and dividends aren't fully accounted for in historical price calculations.

## Troubleshooting

**MPI Error: "invalid rank"**
- Cause: Process count mismatch or leftover zombie processes
- Fix: `pkill -f main.py` and retry with correct `-np` value
- Start with `-np 2` or `-np 4` to test

**Database Lock / "database is locked"**
- Cause: Multiple processes writing simultaneously or abnormal termination
- Fix: Kill processes, restore backup, and retry:
  ```bash
  pkill -f python3
  cp data/canslim.db.initial data/canslim.db
  mpirun -np 2 python3 main.py --mode bulk
  ```

**Out of Memory**
- Cause: Too many processes collecting results at once
- Fix: Use fewer processes or adjust batch size in `main.py` line 55

**Slow Performance**
- Cause: I/O bottleneck with SQLite
- Fix: Use fewer processes (4-6 optimal) or switch to PostgreSQL for production

**Empty Rankings Table**
- Cause: Database not populated with price/earnings data
- Fix: Make sure stooq data is downloaded and unzipped into `data/raw/stooq/`. Then verify tables are populated:
  ```sql
  SELECT COUNT(*) FROM price_bars;
  SELECT COUNT(*) FROM financials;
  ```
  If empty, run data loader script (see data/ directory) before running rankings.
