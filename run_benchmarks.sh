#!/bin/bash
# Benchmark: MPI performance measurement with 3 runs per process count
# Calculates speedup and Karp-Flatt metric

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
NUM_RUNS=3

# Clear previous results
rm -f "$OUTPUT"

echo "Benchmark Results - $(date)" > "$OUTPUT"
echo "Performance Analysis: 3 runs per process count" >> "$OUTPUT"
echo "======================================" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Associative arrays for storing times
declare -A avg_times
baseline_time=0
baseline_time_2procs=0

for nprocs in "${nprocs_list[@]}"; do
    echo "Running with $nprocs process(es) ($NUM_RUNS runs)..."
    
    total_time=0
    
    for run in $(seq 1 $NUM_RUNS); do
        echo "  Run $run/$NUM_RUNS..."
        
        # Clear database before each run
        python3 -c "from db import clear_rankings; clear_rankings()" 2>/dev/null || true
        python3 -c "from db import clear_raw_factors; clear_raw_factors()" 2>/dev/null || true

        start=$(date +%s%N)
        mpirun -np $nprocs --use-hwthread-cpus python3 main.py --mode bulk --days 252 || true
        end=$(date +%s%N)
        
        # Convert nanoseconds to seconds (divide by 1e9)
        time_sec=$(awk "BEGIN {printf \"%.2f\", ($end - $start) / 1000000000}")
        total_time=$(awk "BEGIN {printf \"%.2f\", $total_time + $time_sec}")
        echo "    Time: ${time_sec}s"
    done
    
    # Calculate average
    avg_time=$(awk "BEGIN {printf \"%.2f\", $total_time / $NUM_RUNS}")
    avg_times[$nprocs]=$avg_time
    
    if [ $nprocs -eq 1 ]; then
        baseline_time=$avg_time
    elif [ $nprocs -eq 2 ]; then
        baseline_time_2procs=$avg_time
    fi
    
    echo "$nprocs processes: Average ${avg_time}s"
    read -t 10 -p "Continue? ([y]/n): " continueItteration || continueItteration="y"
    if [[ -z "$continueItteration" ]]; then
        continueItteration="y"
    fi
    if [[ "$continueItteration" != "y" ]]; then
        echo "Benchmarking stopped by user."
        break
    fi
done

# Generate results table
echo "| Processes | Avg Time (s) | Speedup | Speedup (2PCs) | Efficiency | Efficiency (2PCs) | Karp-Flatt (e) | Karp-Flatt (e - 2PCs) |" >> "$OUTPUT"
echo "|-----------|--------------|---------|----------------|------------|-------------------|----------------|-----------------------|" >> "$OUTPUT"

for nprocs in "${nprocs_list[@]}"; do
    if [[ -z "${avg_times[$nprocs]}" ]]; then
        continue
    fi
    
    time_val=${avg_times[$nprocs]}
    speedup=$(awk "BEGIN {printf \"%.3f\", $baseline_time / $time_val}")
    speedup_2procs=$(awk "BEGIN {printf \"%.3f\", $baseline_time_2procs / $time_val}")
    efficiency=$(awk "BEGIN {printf \"%.3f\", $speedup / $nprocs}")
    efficiency_2procs=$(awk "BEGIN {printf \"%.3f\", $speedup_2procs / $nprocs}")
    
    # Karp-Flatt metric: e = (1/S - 1/p) / (1 - 1/p)
    # Only meaningful for p > 1; set to 0 for baseline
    if [ $nprocs -eq 1 ]; then
        karp_flatt="0.000000"
        karp_flatt_2procs="0.000000"
    elif (( $(awk "BEGIN {print ($speedup > 0) ? 1 : 0}") )); then
        inv_p=$(awk "BEGIN {printf \"%.6f\", 1 / $nprocs}")
        inv_s=$(awk "BEGIN {printf \"%.6f\", 1 / $speedup}")
        karp_flatt=$(awk "BEGIN {printf \"%.6f\", ($inv_s - $inv_p) / (1 - $inv_p)}")
        inv_s_2procs=$(awk "BEGIN {printf \"%.6f\", 1 / $speedup_2procs}")
        karp_flatt_2procs=$(awk "BEGIN {printf \"%.6f\", ($inv_s_2procs - $inv_p) / (1 - $inv_p)}")
    else
        karp_flatt="N/A"
        karp_flatt_2procs="N/A"
    fi
    echo "    $nprocs processes: ${time_val}s, Speedup: ${speedup}, Speedup (2PCs): ${speedup_2procs}, Efficiency: ${efficiency}, Efficiency (2PCs): ${efficiency_2procs}, Karp-Flatt: ${karp_flatt}, Karp-Flatt (2PCs): ${karp_flatt_2procs}"

    
    printf "| %9d | %12s | %7s | %14s | %10s | %17s | %14s | %21s |\n" "$nprocs" "$time_val" "$speedup" "$speedup_2procs" "$efficiency" "$efficiency_2procs" "$karp_flatt" "$karp_flatt_2procs" >> "$OUTPUT"
done

echo "" >> "$OUTPUT"
echo "Baseline (1 process): ${baseline_time}s" >> "$OUTPUT"
echo "Baseline (2 processes): ${baseline_time_2procs}s" >> "$OUTPUT"
echo "" >> "$OUTPUT"
echo "Metrics Explanation:" >> "$OUTPUT"
echo "- Speedup: T_1 / T_p (how many times faster with p processes)" >> "$OUTPUT"
echo "- Efficiency: Speedup / p (fraction of ideal parallelization achieved)" >> "$OUTPUT"
echo "- Karp-Flatt: Serial fraction of code; lower is better" >> "$OUTPUT"
echo "" >> "$OUTPUT"

echo "Results saved to: $OUTPUT"
cat "$OUTPUT"
echo "Done"
