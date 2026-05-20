#!/bin/bash
# Benchmark: MPI performance measurement

set -e

if [ "$1" == "--reverse" ]; then
    nprocs_list=(12 8 6 4 2 1)
else
    nprocs_list=(1 2 4 6 8 12)
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PROJECT_DIR}/.venv"

source "${VENV_DIR}/bin/activate"

OUTPUT="${PROJECT_DIR}/BENCHMARK_RESULTS.txt"

# Clear previous results
rm -f "$OUTPUT"

echo "Benchmark Results - $(date)" > "$OUTPUT"
echo "======================================" >> "$OUTPUT"
echo "" >> "$OUTPUT"
echo "| Processes | Time (ms) | Speedup |" >> "$OUTPUT"
echo "|-----------|-----------|---------|" >> "$OUTPUT"

# Store baseline
baseline_time=0
times_table=()

for nprocs in "${nprocs_list[@]}"; do
    echo "Running with $nprocs process(es)..."
    
    #clear database with python script before each run
    python3 -c "from db import clear_rankings; clear_rankings()"
    python3 -c "from db import clear_raw_factors; clear_raw_factors()"

    start=$(date +%s%N)
    mpirun -np $nprocs --use-hwthread-cpus python3 main.py --mode bulk 2>&1 || true
    end=$(date +%s%N)
    
    # Convert to seconds
    time_ms=$(((end - start) / 1000000000))
    
    if [ $nprocs -eq 1 ]; then
        baseline_time=$time_ms
        speedup="1.000"
    fi
    
    echo "$nprocs processes: ${time_ms}s"
    times_table+=($time_ms)
    timeout 10 read -p "Continue to next iteration? ([y]/n): " continueItteration
    if [ $? -ne 0 ]; then
        echo "No input received. Continuing to next iteration..."
        continueItteration="y"
    fi
    if [[ -z "$continueItteration" ]]; then
        continueItteration="y"
    fi
    if [[ "$continueItteration" != "y" ]]; then
        echo "Benchmarking stopped by user."
        break
    fi
done

idx=0
for time_ms in "${times_table[@]}"; do
    speedup=$(echo "scale=3; $time_ms / $baseline_time" | bc)
    printf "| %9d | %9d | %7s |\n" ${nprocs_list[$idx]} $time_ms "$speedup" >> "$OUTPUT"
    ((idx++))
done

echo "" >> "$OUTPUT"
echo "Results saved to: $OUTPUT"
cat "$OUTPUT"
echo "Done"
