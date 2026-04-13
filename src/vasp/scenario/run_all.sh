#!/bin/bash
# =============================================
#  run_all.sh  - Running all experiments: (5 detectors x 3 scenarios = 15)
# =============================================
cd "$(dirname "$0")"

CONFIGS=(
    "B0_Baseline" "B1_Baseline" "B2_Baseline" "B3_Baseline" "P_Baseline"
    "B0_A1" "B1_A1" "B2_A1" "B3_A1" "P_A1"
    "B0_A2" "B1_A2" "B2_A2" "B3_A2" "P_A2"
)

TOTAL=${#CONFIGS[@]}
COUNT=0

echo "============================================="
echo "  Running all experiments:: $TOTAL configs"
echo "============================================="
echo ""

for cfg in "${CONFIGS[@]}"; do
    COUNT=$((COUNT + 1))
    echo "[$COUNT/$TOTAL] Running: $cfg"
    START=$(date +%s)

    ./run -u Cmdenv -c "$cfg" omnetpp.ini 2>&1 | tail -3

    END=$(date +%s)
    echo "  Done: $((END - START))s"
    echo ""
done

echo "============================================="
echo "  All experiments complete!"
echo "  Results: results/"
echo "============================================="
echo ""
echo "Analyze results:"
echo "  ./analyze_results.sh"


# Ablation
for CFG in P_NoGate_Baseline P_NoGate_A1 P_NoGate_A2; do
  echo "-- Running $CFG --"
  ./run -u Cmdenv -c $CFG omnetpp.ini 2>&1 | tail -3
done
