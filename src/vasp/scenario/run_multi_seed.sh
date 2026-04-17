#!/bin/bash
# ===============================================================
#  run_multi_seed.sh -- Phase 1: Multi-Seed Experiments
#  
#  5 seeds x (5 baselines + 10 attacks + 3 ablation) = 90 runs
#  Estimated: ~2 hours
# ===============================================================

set -e
cd "$(dirname "$0")"

N_SEEDS=5

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# -- Pre-flight checks --
echo -e "${CYAN}===================================================${NC}"
echo -e "${CYAN}  Phase 1: Multi-Seed Experiments (${N_SEEDS} seeds)${NC}"
echo -e "${CYAN}===================================================${NC}"

for s in $(seq 0 $((N_SEEDS - 1))); do
    if [ ! -f "highway_seed${s}.rou.xml" ]; then
        echo -e "${RED}ERROR: highway_seed${s}.rou.xml not found!${NC}"
        echo "Run first: python3 generate_route_variants.py $N_SEEDS"
        exit 1
    fi
done

if [ ! -f "highway_original.rou.xml" ]; then
    cp highway.rou.xml highway_original.rou.xml
    echo -e "${GREEN}  Backed up highway.rou.xml -> highway_original.rou.xml${NC}"
fi

mkdir -p results

# -- Config lists --
CONFIGS=(
    "B0_Baseline" "B1_Baseline" "B2_Baseline" "B3_Baseline" "P_Baseline"
    "B0_A1" "B1_A1" "B2_A1" "B3_A1" "P_A1"
    "B0_A2" "B1_A2" "B2_A2" "B3_A2" "P_A2"
    "P_NoGate_Baseline" "P_NoGate_A1" "P_NoGate_A2"
)
TOTAL_PER_SEED=${#CONFIGS[@]}
TOTAL_ALL=$((TOTAL_PER_SEED * N_SEEDS))

echo -e "  Configs per seed: ${TOTAL_PER_SEED}"
echo -e "  Total runs: ${TOTAL_ALL}"
echo ""

GLOBAL_START=$(date +%s)
GLOBAL_COUNT=0

for SEED in $(seq 0 $((N_SEEDS - 1))); do
    echo -e "${CYAN}==============================================${NC}"
    echo -e "${CYAN}  Seed ${SEED}/${N_SEEDS}${NC}"
    echo -e "${CYAN}==============================================${NC}"

    # Swap route file
    cp "highway_seed${SEED}.rou.xml" highway.rou.xml
    echo -e "  Route: highway_seed${SEED}.rou.xml"

    # Clean detlogs from previous configs (avoid mixing)
    rm -f results/detlog-*.csv

    COUNT=0
    for cfg in "${CONFIGS[@]}"; do
        COUNT=$((COUNT + 1))
        GLOBAL_COUNT=$((GLOBAL_COUNT + 1))
        echo -ne "  ${YELLOW}[${GLOBAL_COUNT}/${TOTAL_ALL}]${NC} seed${SEED}/${cfg}... "
        START=$(date +%s)

        ./run -u Cmdenv -c "$cfg" --seed-set=$SEED omnetpp.ini > /dev/null 2>&1

        END=$(date +%s)
        echo -e "${GREEN}done${NC} ($((END - START))s)"
    done

    # Move results to seed directory
    mkdir -p "results/seed${SEED}"
    mv results/detlog-*.csv "results/seed${SEED}/" 2>/dev/null || true
    
    N_FILES=$(ls results/seed${SEED}/detlog-*.csv 2>/dev/null | wc -l)
    echo -e "  ${GREEN}-> results/seed${SEED}/ (${N_FILES} files)${NC}"
    echo ""
done

# Restore original route file
cp highway_original.rou.xml highway.rou.xml
echo -e "${GREEN}Restored original highway.rou.xml${NC}"

GLOBAL_END=$(date +%s)
ELAPSED=$((GLOBAL_END - GLOBAL_START))
MINUTES=$((ELAPSED / 60))

echo ""
echo -e "${CYAN}===================================================${NC}"
echo -e "${GREEN}  Complete! ${GLOBAL_COUNT} runs in ${MINUTES}m ${ELAPSED}s${NC}"
echo -e "${CYAN}===================================================${NC}"
echo ""
echo "Results:"
for s in $(seq 0 $((N_SEEDS - 1))); do
    N=$(ls results/seed${s}/detlog-*.csv 2>/dev/null | wc -l)
    echo "  results/seed${s}/ -> ${N} files"
done
echo ""
echo "Next: python3 analyze_multi_seed.py results/"
