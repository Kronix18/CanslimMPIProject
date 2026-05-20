# Setup Utilities

This directory contains one-time setup and data population scripts that are **not used** by the main MPI processing pipeline (main.py).

These scripts are only needed for:
- Initial database setup
- Data population and caching
- Code maintenance and refactoring

## Scripts

### Data Population
- **populate_universe.py** - Load S&P 500 constituents into the universe table
- **load_stooq_data.py** - Download and cache OHLCV price bars from stooq.com
- **fetch_sec_financials.py** - Fetch and cache financial data from SEC EDGAR

### Database Maintenance
- **rebuild_universe.py** - Rebuild universe data (clear and repopulate)

### Code Maintenance
- **cleanup_script.py** - Cleanup utility (generated during refactoring)
- **simplify_code.py** - Code simplification script v1
- **simplify_code_v2.py** - Code simplification script v2
- **simplify_code_v3.py** - Code simplification script v3

## Usage

These scripts should generally not be needed after initial setup. The main MPI pipeline (main.py) handles all data collection and processing automatically.

### If you need to reset the database:
```bash
cd /tank/data/RSS/HPC/project
python3 setup_utilities/rebuild_universe.py
python3 setup_utilities/load_stooq_data.py
python3 setup_utilities/fetch_sec_financials.py
```

### Main Processing (after setup):
```bash
cd /tank/data/RSS/HPC/project
mpirun -np 4 python3 main.py
```

## Core Pipeline Files

The actual MPI processing pipeline uses these core files (located in parent directory):
- `main.py` - MPI orchestrator
- `repository.py` - Database persistence
- `data_collection.py` - Data fetching
- `technical_calcs.py` - Technical metrics
- `financial_calcs.py` - Financial metrics
- `ranking.py` - CAN SLIM scoring
- `schemas.py` - Data validation
- `logging_config.py` - Logging setup
- `universe.py` - Universe helpers
- `data_quality.py` - Quality validation
- `benchmark.py` - Performance benchmarking
