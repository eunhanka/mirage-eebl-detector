# Experiment Guide

## Prerequisites
- Ubuntu 20.04+ (tested on 24.04)
- OMNeT++ 5.7+ with C++14
- SUMO 1.8.0+
- Veins 5.2 with VASP
- Python 3.8+ (numpy, pandas, matplotlib, scikit-learn)

## Running All Experiments

    # Start SUMO daemon
    python3 /path/to/veins-5.2/sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &

    # Run 15 main + 3 ablation experiments (~20 min)
    cd /path/to/veins-5.2/src/vasp/scenario
    ./run_all.sh

    # Analyze and generate figures
    python3 analyze_vasp_v3.py results/

## Configurations (omnetpp.ini)

| Config | Detector | Scenario |
|--------|----------|----------|
| B0/B1/B2/B3/P_Baseline | All | No attack |
| B0/B1/B2/B3/P_A1 | All | FakeEEBL_NoStop |
| B0/B1/B2/B3/P_A2 | All | FakeEEBL_WithStop |
| P_NoGate_* | Ablation | Without EEBL gating |

## Detector Types (detectorType)
- 0: No Detection (B0)
- 1: Threshold (B1)
- 2: VCADS (B2)
- 3: F2MD/VASP (B3)
- 4: MIRAGE (Proposed)

## Attack Types (attackType)
- 0: No attack (Baseline)
- 10: A1 FakeEEBL_NoStop
- 11: A2 FakeEEBL_WithStop

## Output
- Detection logs: results/detlog-*.csv
- Figures: results/figures/
- LaTeX table: results/table_comparison.tex
