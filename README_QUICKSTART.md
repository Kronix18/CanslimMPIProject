# HPC CANSLIM Stock Ranking Pipeline

This is a distributed stock ranking system that evaluates 503+ stocks daily using CANSLIM factors (a popular stock selection methodology). It ranks them on a scale of 99 (best) to 1 (worst) based on earnings growth, price momentum, volume, and other fundamentals.

## Quick Start

First, set up your environment:

```bash
cd /tank/data/RSS/HPC/project
source .venv/bin/activate
```

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
- `universe`: Your 503 stocks with basic info
- `price_bars`: Daily prices going back years
- `financials`: Quarterly and annual earnings data
- `raw_factors`: The calculated C, A, N, S, L scores for each stock-date
- `rankings`: The final 99-1 rankings with composite scores

## Performance

How long things take depends on how many cores you throw at it:

The SQLite database can only write from one process at a time, so after about 8 cores you don't get much faster.

This could be mitigated in the future by using a database with concurent write options (PostgreSQL)

## Configuration

Edit `config.yaml` if you want to change the project name or database location. That's about it.

## Example: Get Today's Top 10

```sql
SELECT ticker, final_rank, composite_score, c_norm, a_norm, n_norm, s_norm, l_norm
FROM rankings
WHERE data_date = DATE('now')
ORDER BY final_rank DESC
LIMIT 10;
```

## Heads Up

A few things to know about the current implementation:

- The I factor (institutional ownership) just always returns 0 because we don't have that data
- Market regime (M factor) is hardcoded to "Confirmed Uptrend" for now
- If a stock doesn't have 252 days of price data or quarterly earnings, it scores lower
- Missing financial data gets treated as zero instead of being filled in

## If Something Breaks

If MPI complains about invalid ranks, make sure your `-np` value is correct. Start with 1 or 2 processes to test.

If you get database lock errors, kill any stray Python processes and restore from backup:
```bash
pkill -f main.py
cp data/canslim.db.initial data/canslim.db
```

If it runs out of memory, either use fewer processes or modify `main.py` to collect results in smaller batches.
