# MIRAGE: Detecting Fake EEBL Attacks in V2X Networks via Event-Gated Behavioral Analysis

Implementation of **MIRAGE** (Multi-stage Inspection and Response Against Ghost-vehicle EEBL), an event-gated detector for fake Emergency Electronic Brake Light attacks in V2X networks. Built on [VASP](https://github.com/quic/vasp) / [Veins 5.2](https://veins.car2x.org/) / [SUMO](https://sumo.dlr.de/).

## Overview

MIRAGE activates only under EEBL conditions and evaluates four stages of evidence:

| Stage | Checks | Target |
|-------|--------|--------|
| **Stage 1** Context Assessment | TTC plausibility, new-sender detection | Suspicious EEBL context |
| **Stage 2** Deceleration Plausibility | Physical limits, cross-field consistency, brake-speed mismatch | Kinematic anomalies |
| **Stage 3** Behavioral Consistency | Trajectory, position-derived speed, position-speed mismatch | A1 trajectory divergence |
| **Stage 4** Post-Stop Consistency | Frozen position detection | A2 post-attack artifacts |
| **IDM Mitigation** | Physics-based deceleration bounding | Fail-safe for missed detections |

## Key Results

Results reported as mean +/- std across 5 independent seeds (see [`run_multi_seed.sh`](src/vasp/scenario/run_multi_seed.sh) for reproduction).

| Method | TPR | FPR | Precision | F1 |
|--------|-----|-----|-----------|-----|
| B1: Threshold    | 0.597 +/- 0.003 | 0.009 +/- 0.001 | 0.950 +/- 0.009 | 0.733 +/- 0.004 |
| B2: VCADS        | 0.499 +/- 0.000 | 0.040 +/- 0.011 | 0.778 +/- 0.059 | 0.607 +/- 0.018 |
| B3: F2MD/VASP    | 0.110 +/- 0.003 | 0.009 +/- 0.001 | 0.770 +/- 0.037 | 0.193 +/- 0.006 |
| **MIRAGE**       | **0.883 +/- 0.003** | **0.009 +/- 0.001** | **0.965 +/- 0.007** | **0.922 +/- 0.001** |

**Per-attack breakdown** (TPR): MIRAGE is the only detector with high detection on both attack variants: A1 (NoStop) 77.0%, A2 (WithStop) 99.7%. Baselines specialize on one variant each. IDM mitigation reduces mean braking severity by 75%.

## Repository Structure

    src/vasp/
    |-- driver/
    |   |-- CarApp.cc             # Modified: detection logging, IDM mitigation
    |   |-- CarApp.h              # Modified: detector type enum
    |   |-- CarApp.ned            # Modified: detector parameters
    |-- mdm/
    |   |-- MisbehaviorDetectors.h    # All detector implementations
    |   |-- ProposedIDMDetector.cc    # Proposed detector module
    |   |-- ProposedIDMDetector.h     # Proposed detector header
    |-- scenario/
        |-- omnetpp.ini               # 18 experiment configurations
        |-- run_all.sh                # Single-seed batch runner (15 configs + 3 ablations)
        |-- run_multi_seed.sh         # Multi-seed runner (5 seeds x 18 configs = 90 runs)
        |-- generate_route_variants.py # Generates per-seed SUMO route files
        |-- analyze_vasp_v3.py        # Single-seed analysis and figures
        |-- analyze_multi_seed.py     # Multi-seed analysis, paper figures, LaTeX tables
        |-- traci_braking.py          # TraCI braking event controller
        |-- highway.net.xml           # SUMO network
        |-- ...                       # Additional SUMO scenario files
    docs/
    |-- EXPERIMENT_GUIDE.md

## Quick Start

### Prerequisites
- OMNeT++ 5.6.2 (tested; VASP requires this version, see [VASP requirements](https://github.com/quic/vasp#dependencies))
- SUMO 1.8.0
- Veins 5.2 with VASP submodule
- Python 3.8+ (numpy, pandas, matplotlib, scikit-learn)
- Ubuntu 20.04 LTS (tested)

### Install
Follow the [VASP guide](https://github.com/quic/vasp#readme), then:

    cp -r src/vasp/driver/* /path/to/veins-5.2/src/vasp/driver/
    cp -r src/vasp/mdm/*    /path/to/veins-5.2/src/vasp/mdm/
    cp -r src/vasp/scenario/* /path/to/veins-5.2/src/vasp/scenario/
    cd /path/to/veins-5.2 && ./configure && make -j$(nproc)

### Run

MIRAGE provides two reproduction paths. Use **multi-seed** for matching the paper's reported mean +/- std (Table 4); use **single-seed** for a quick sanity check.

#### Option A: Single-seed (~20 min)

    python3 sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &
    cd src/vasp/scenario && ./run_all.sh
    python3 analyze_vasp_v3.py results/

#### Option B: Multi-seed, reproduces paper results (~2 h)

    python3 sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &
    cd src/vasp/scenario

    # Generate per-seed SUMO routes (run once)
    python3 generate_route_variants.py 5

    # Run all 90 experiments (5 seeds x 18 configs)
    ./run_multi_seed.sh

    # Analyze: paper figures + LaTeX tables with mean +/- std
    python3 analyze_multi_seed.py results/

Multi-seed outputs: `results/seed{0..4}/` detlogs, `results/figures/` (fig2_roc, fig3_per_attack, fig5_sensitivity, fig_mitigation), and `results/figures/tab_*.tex` LaTeX tables.

See [docs/EXPERIMENT_GUIDE.md](docs/EXPERIMENT_GUIDE.md) for details.

## Detection Checks and Weights

| Check | Description | Weight |
|-------|-------------|--------|
| 1a | TTC plausibility (high) | 0.15 |
| 1a' | TTC plausibility (receding) | 0.35 |
| 1b | New sender | 0.20 |
| 2a | Physical deceleration limit | 0.20 |
| 2b | Cross-field consistency | 0.15 |
| 2c | Brake-speed mismatch | 0.15 |
| 3a | Trajectory consistency | 0.20 |
| 3b | Position-derived speed | 0.30 |
| 3c | Position-speed mismatch | 0.15 |
| 4 | Frozen position after stop | 0.60 |

Detection threshold: Theta = 0.55

## License

MIT License (consistent with [VASP](https://github.com/quic/vasp)). See [LICENSE](LICENSE).

## Acknowledgments

- [VASP](https://github.com/quic/vasp) by Qualcomm Innovation Center
- [Veins](https://veins.car2x.org/), [SUMO](https://sumo.dlr.de/)
- Supported by USDOT TraCR [Grant: 11543]
