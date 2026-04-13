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

| Method | TPR | FPR | Precision | F1 |
|--------|-----|-----|-----------|-----|
| B1: Threshold | 0.597 | 0.009 | 0.950 | 0.733 |
| B2: VCADS | 0.499 | 0.040 | 0.778 | 0.607 |
| B3: F2MD/VASP | 0.110 | 0.009 | 0.770 | 0.193 |
| **MIRAGE** | **0.883** | **0.009** | **0.965** | **0.922** |

MIRAGE is the **only detector with high detection on both attack variants**: 77.0% on A1 (NoStop), 99.7% on A2 (WithStop). IDM mitigation reduces mean braking severity by 75%.

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
        |-- run_all.sh                # Batch runner
        |-- analyze_vasp_v3.py        # Analysis and paper figures
        |-- highway.net.xml           # SUMO network
        |-- ...                       # Additional scenario files
    docs/
    |-- EXPERIMENT_GUIDE.md

## Quick Start

### Prerequisites
- OMNeT++ 5.7+, SUMO 1.8.0+, Veins 5.2, VASP
- Python 3.8+ (numpy, pandas, matplotlib, scikit-learn)

### Install
Follow the [VASP guide](https://github.com/quic/vasp#readme), then:

    cp -r src/vasp/driver/* /path/to/veins-5.2/src/vasp/driver/
    cp -r src/vasp/mdm/*    /path/to/veins-5.2/src/vasp/mdm/
    cp -r src/vasp/scenario/* /path/to/veins-5.2/src/vasp/scenario/
    cd /path/to/veins-5.2 && ./configure && make -j$(nproc)

### Run

    python3 sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &
    cd src/vasp/scenario && ./run_all.sh
    python3 analyze_vasp_v3.py results/

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
