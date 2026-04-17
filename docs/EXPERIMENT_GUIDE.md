# Experiment Guide

This guide describes the end-to-end workflow for reproducing MIRAGE's
experimental results, including both a single-seed sanity check and the
multi-seed reproduction of the paper's `mean +/- std` results.

## 1. Prerequisites

The stack below is the one verified in the paper; versions are pinned
intentionally because VASP is tied to a specific OMNeT++/Veins release.

- Ubuntu 20.04 LTS (tested; 22.04+ is untested with OMNeT++ 5.6.2)
- OMNeT++ 5.6.2 with `CXXFLAGS=-std=c++14` enabled in `configure.user`
- SUMO 1.8.0 (newer versions may work but are untested)
- Veins 5.2 with the VASP submodule
- Python 3.8+ with `numpy`, `pandas`, `matplotlib`, `scikit-learn`
- GCC 9.4 (Ubuntu 20.04 default) with C++14 support

Refer to the [VASP README](https://github.com/quic/vasp#readme) for the
authoritative dependency list.

## 2. Installation Notes

Follow the VASP installation guide. Two points commonly missed:

1. **CSVWriter.h and json.h** must be placed in a system include directory
   (typically `/usr/include`). Note that `nlohmann/json` ships as
   `json.hpp` and must be renamed to `json.h`.
2. **OMNeT++ configure.user** must have `CXXFLAGS=-std=c++14` uncommented
   before running `./configure`. Silent C++11 builds will fail with
   template errors in the detector code.

After the VASP stack is built, overlay the MIRAGE source files:

    cp -r mirage-eebl-detector/src/vasp/driver/*   /path/to/veins-5.2/src/vasp/driver/
    cp -r mirage-eebl-detector/src/vasp/mdm/*      /path/to/veins-5.2/src/vasp/mdm/
    cp -r mirage-eebl-detector/src/vasp/scenario/* /path/to/veins-5.2/src/vasp/scenario/
    cd /path/to/veins-5.2 && ./configure && make -j$(nproc)

## 3. Quick Sanity Check (~2 min)

Before the full run, verify the build with a single short experiment:

    # Start SUMO daemon in the background
    python3 /path/to/veins-5.2/sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &

    # Run a single config (MIRAGE + A2 attack)
    cd /path/to/veins-5.2/src/vasp/scenario
    ./run -u Cmdenv -c P_A2 omnetpp.ini

Expected: the simulation completes in under a minute and produces
`results/detlog-P_A2-0-*.csv`. If this fails, do not proceed to the full
runs -- the issue is environmental (SUMO port, veins build, TraCI) and
will affect every config.

## 4. Option A: Single-seed Run (~20 min)

Use this path for development, debugging, or a fast functional check.
Results correspond to the single-seed results reported in the paper.

    # Start SUMO daemon (if not already running)
    python3 /path/to/veins-5.2/sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &

    cd /path/to/veins-5.2/src/vasp/scenario

    # 15 main + 3 ablation configs
    ./run_all.sh

    # Analyze: ROC curves, per-attack TPR, sensitivity, mitigation
    python3 analyze_vasp_v3.py results/

## 5. Option B: Multi-seed Run (~2 h, reproduces paper results)

Use this path to reproduce the paper's main results table and all figures
with `mean +/- std` error reporting across 5 independent seeds.

    # Start SUMO daemon (if not already running)
    python3 /path/to/veins-5.2/sumo-launchd.py -vv -c sumo > /dev/null 2>&1 &

    cd /path/to/veins-5.2/src/vasp/scenario

    # Step 1: Generate per-seed SUMO route files (run once)
    # Creates highway_seed0.rou.xml ... highway_seed4.rou.xml with
    # randomized initial speeds (25 +/- 2 m/s) and inter-vehicle gaps.
    python3 generate_route_variants.py 5

    # Step 2: Execute all 90 runs (5 seeds x 18 configs)
    # Internally uses OMNeT++ --seed-set for RNG injection and
    # swaps highway.rou.xml per seed.
    ./run_multi_seed.sh

    # Step 3: Aggregate across seeds and generate paper artifacts
    python3 analyze_multi_seed.py results/

Outputs are organized as:

    results/
    |-- seed0/ detlog-*.csv     (18 CSV files, one per config)
    |-- seed1/ ...
    |-- ...
    |-- seed4/ ...
    |-- figures/
        |-- fig2_roc.png, .pdf            # ROC with mean+std bands
        |-- fig3_per_attack.png, .pdf     # Per-attack TPR bars
        |-- fig5_sensitivity.png, .pdf    # Threshold sweep
        |-- fig_mitigation.png, .pdf      # IDM braking distribution
        |-- tab_comparison.tex            # Table 4 (main results)
        |-- tab_mitigation.tex            # Table 5 (mitigation)
        |-- tab_latency.tex               # Latency stats
        |-- tab_ablation.tex              # Ablation study

## 6. Configurations (omnetpp.ini)

All 18 configurations follow the pattern `<DET>_<SCENARIO>`:

| Config pattern            | Detector   | Scenario            |
|---------------------------|------------|---------------------|
| `B0/B1/B2/B3/P_Baseline`  | All five   | No attack           |
| `B0/B1/B2/B3/P_A1`        | All five   | FakeEEBL_NoStop     |
| `B0/B1/B2/B3/P_A2`        | All five   | FakeEEBL_WithStop   |
| `P_NoGate_*`              | Ablation   | Without EEBL gating |

### Detector Types (`detectorType`)

- 0: No Detection (B0)
- 1: Threshold (B1)
- 2: VCADS (B2)
- 3: F2MD/VASP (B3)
- 4: MIRAGE (Proposed)

### Attack Types (`attackType`)

- 0: No attack (Baseline)
- 10: A1 FakeEEBL_NoStop
- 11: A2 FakeEEBL_WithStop

### Seed Injection

OMNeT++ RNG is injected via `--seed-set=<N>` passed by `run_multi_seed.sh`.
SUMO randomness comes from per-seed route files with `sigma=0.5` and
`speedDev=0.1`. To change the number of seeds:

    python3 generate_route_variants.py <N>
    # then edit N_SEEDS in run_multi_seed.sh to match

## 7. Expected Timing

| Task                                  | Time       |
|---------------------------------------|------------|
| Single config (e.g., `P_A2`)          | ~40 s      |
| `run_all.sh` (18 configs)             | ~20 min    |
| `run_multi_seed.sh` (90 runs)         | ~2 h       |
| `analyze_multi_seed.py` (all figures) | ~1 min     |

Timings measured on Intel i7, 16 GB RAM, Ubuntu 20.04.

## 8. Troubleshooting

- **`TraCIServer.cc: connect failed`**: SUMO daemon is not running or its
  port is taken. Verify with `lsof -i :9999` and restart `sumo-launchd.py`.
- **`cRuntimeError: no such module type`**: The `driver/` overlay was not
  re-applied after a `make clean`. Re-run the `cp -r` commands from
  section 2 and rebuild.
- **`analyze_multi_seed.py` reports "n_seeds=1"**: The script expects a
  `results/seed0/`, `results/seed1/`, ... layout. If detlogs are in
  `results/` directly, you ran the single-seed flow -- use
  `analyze_vasp_v3.py` instead.
- **Figures look different from the paper**: small variation (+/-0.01 in
  F1) is expected across different CPUs due to floating-point reduction
  order. Magnitudes and ranking should match the paper exactly.

## 9. Output File Formats

Detection log (`detlog-<CONFIG>-<RUN>-<TIMESTAMP>.csv`):

| Column        | Description                                       |
|---------------|---------------------------------------------------|
| `time`        | Simulation time (s)                               |
| `hv_id`       | Host vehicle ID (receiver)                        |
| `rv_id`       | Remote vehicle ID (sender)                        |
| `attack_type` | Ground-truth attack label                         |
| `det_name`    | Detector name (e.g., `P_Proposed`)                |
| `suspicious`  | 1 if score >= Theta, else 0                       |
| `score`       | Weighted anomaly score (0.0-1.0+)                 |
| `reason`      | `|`-separated list of triggered checks            |
| `ttc`         | Time-to-collision estimate                        |
| `mitigated_a` | IDM-bounded acceleration (m/s^2)                  |
