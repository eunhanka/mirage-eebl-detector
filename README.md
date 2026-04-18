# MIRAGE: Detecting Fake EEBL Attacks in V2X Networks via Event-Gated Behavioral Analysis

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19639253.svg)](https://doi.org/10.5281/zenodo.19639253)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Ubuntu](https://img.shields.io/badge/Ubuntu-20.04%20LTS-orange.svg)](https://releases.ubuntu.com/20.04/)

This is the artifact accompanying the paper **"MIRAGE: Detecting Fake
Emergency Electronic Brake Light Attacks in V2X Networks via Event-Gated
Behavioral Analysis"** (*VehicleSec '26*). The preprint is at
[`paper/VehicleSec26_MIRAGE.pdf`](paper/VehicleSec26_MIRAGE.pdf).

Built on top of [VASP](https://github.com/quic/vasp) /
[Veins 5.2](https://veins.car2x.org/) /
[SUMO 1.8.0](https://sumo.dlr.de/) /
[OMNeT++ 5.6.2](https://omnetpp.org/).

---

## Table of contents

1. [Overview](#overview)
2. [Key results](#key-results)
3. [Quick start for artifact reviewers](#quick-start-for-artifact-reviewers)
4. [Repository layout](#repository-layout)
5. [Detection checks and weights](#detection-checks-and-weights)
6. [Re-running from scratch](#re-running-from-scratch)
7. [Reproduction expectations](#reproduction-expectations)
8. [Troubleshooting](#troubleshooting)
9. [Citation](#citation)
10. [License and acknowledgments](#license-and-acknowledgments)

---

## Overview

MIRAGE (Multi-stage Inspection and Response Against Ghost-vehicle EEBL)
activates only under EEBL conditions and evaluates four stages of
evidence:

| Stage | Checks | Target |
|---|---|---|
| 1 — Context Assessment | TTC plausibility, new-sender detection | Suspicious EEBL context |
| 2 — Deceleration Plausibility | Physical limits, cross-field consistency, brake-speed mismatch | Kinematic anomalies |
| 3 — Behavioral Consistency | Trajectory, position-derived speed, position-speed mismatch | A1 trajectory divergence |
| 4 — Post-Stop Consistency | Frozen position detection | A2 post-attack artifacts |
| IDM Mitigation | Physics-based deceleration bounding | Fail-safe for missed detections |

## Key results

| Method | TPR | FPR | Precision | F1 |
|---|---|---|---|---|
| B1: Threshold | 0.597 | 0.009 | 0.950 | 0.733 |
| B2: VCADS | 0.499 | 0.040 | 0.778 | 0.607 |
| B3: F2MD/VASP | 0.110 | 0.009 | 0.770 | 0.193 |
| **MIRAGE** | **0.883** | **0.009** | **0.965** | **0.922** |

MIRAGE is the **only detector with high detection on both attack
variants**: 77.0 % on A1 (NoStop) and 99.7 % on A2 (WithStop). The IDM
mitigation layer reduces mean braking severity by ≈ 75 %. Full paper
claims and tolerances: [`CLAIMS.md`](CLAIMS.md).

---

## Quick start for artifact reviewers

### A. One-shot install and smoke test (≈ 15 minutes)

Starting from a fresh **Ubuntu 20.04** host (or a VM / container on that
base image), no other dependencies required:

```bash
git clone --branch artifact-evaluation \
    https://github.com/eunhanka/mirage-eebl-detector.git
cd mirage-eebl-detector

sudo ./scripts/install.sh all          # builds OMNeT++, SUMO, Veins, VASP, MIRAGE
./scripts/quick_test.sh                # P_A2 end-to-end, expect ~2 min runtime
```

`quick_test.sh` runs the A2 (WithStop) attack configuration with the MIRAGE
detector, and asserts that the detection log records > 0 flagged BSMs.
On success it prints `Quick test PASSED` and exits 0.

### B. Single-seed full reproduction (~ 10 minutes after install)

```bash
./scripts/run_single_seed.sh 0         # all 18 configs, seed 0
./scripts/verify_results.py --seeds 0  # compare vs CLAIMS.md
```

### C. Full 5-seed paper reproduction (~ 1 hour after install)

```bash
cd /opt/mirage/veins-5.2/src/vasp/scenario
./run_multi_seed.sh 0 1 2 3 4
cd -
./scripts/verify_results.py --all --seeds 0 1 2 3 4
```

---

## Repository layout

    mirage-eebl-detector/
    ├── CLAIMS.md                     # Reference values + tolerances per RQ
    ├── paper/
    │   └── VehicleSec26_MIRAGE.pdf
    ├── scripts/
    │   ├── install.sh                # 5-stage dispatcher: deps/omnetpp/sumo/veins/mirage
    │   ├── lib/
    │   │   ├── 01_deps.sh            # apt, pip, headers
    │   │   ├── 02_omnetpp.sh         # OMNeT++ 5.6.2 from source
    │   │   ├── 03_sumo.sh            # SUMO 1.8.0 from source
    │   │   ├── 04_veins.sh           # Veins 5.2 + VASP (pinned commits)
    │   │   └── 05_mirage.sh          # MIRAGE overlay + rebuild
    │   ├── quick_test.sh             # P_A2 end-to-end smoke test
    │   ├── run_single_seed.sh        # Run all 18 configs for one seed
    │   └── verify_results.py         # Compare re-run vs CLAIMS.md
    ├── src/vasp/                     # MIRAGE overlay applied on top of vanilla VASP
    │   ├── driver/
    │   │   ├── CarApp.cc / .h / .ned # Extended with detection logging + IDM mitigation
    │   ├── mdm/
    │   │   └── MisbehaviorDetectors.h# All detectors (B0–B3, Proposed, NoGate) inline
    │   └── scenario/
    │       ├── omnetpp.ini           # 18 experimental configurations
    │       ├── highway.{net,rou,add,launchd,sumocfg}.xml
    │       ├── highway.junctions.json
    │       ├── vss_schedule.xml      # Leader-brake schedule
    │       ├── generate_route_variants.py  # Per-seed routes
    │       ├── run_all.sh            # Single-seed, all configs
    │       ├── run_multi_seed.sh     # 5-seed driver
    │       ├── analyze_vasp_v3.py    # Paper figures + tables
    │       └── analyze_multi_seed.py # Multi-seed aggregation
    └── reference_results/
        ├── figures/                  # Paper figures (PNG + PDF)
        ├── tables/                   # LaTeX sources for Tables 4–6
        └── README.md                 # How to interpret

The sanity of every path above is enforced by `scripts/lib/05_mirage.sh`
(`EXPECTED_OVERLAY_FILES`) so any missing overlay file aborts the install
before the build runs.

## Detection checks and weights

| Check | Description | Weight |
|---|---|---|
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

Detection threshold Θ = 0.55 at the operating point; see paper §7.4 for
the sensitivity analysis over Θ ∈ [0.0, 1.0].

---

## Re-running from scratch

### Requirements

- Ubuntu 20.04 LTS (other distributions may work but are not tested by
  the install pipeline)
- ≥ 4 CPU cores (16 recommended for faster rebuilds)
- ≥ 8 GB RAM
- ≥ 20 GB free disk (source builds + logs; raw results ~6 GB additional)
- Network access during `install.sh deps` and `install.sh omnetpp/sumo/veins`

### Pinned versions

The install pipeline pins every exotic dependency to an exact commit /
tag so reviewers can reproduce bit-by-bit builds:

| Component | Version | Commit / tag |
|---|---|---|
| OMNeT++ | 5.6.2 | upstream release tarball |
| SUMO | 1.8.0 | tag `v1_8_0` |
| Veins | 5.2 | `c5b4d7c4fab0e2b23f78d2e4f90a7ebc512db596` (tag `veins-5.2`) |
| VASP | — | `0ec4af324f3ed729690f1cbd1b1143ebd7f4d6f4` |

Changing these versions is not supported and may break the build because
C++ interface changes between OMNeT++ / Veins versions.

### Install stages

`scripts/install.sh` dispatches to five stage scripts. Each stage is
idempotent: running it a second time detects the prior result and
skips the build.

```bash
sudo ./scripts/install.sh deps      # apt + pip + C++ headers
sudo ./scripts/install.sh omnetpp   # ~20–40 min on 4 cores; ~1 min rebuild
sudo ./scripts/install.sh sumo      # ~5–10 min
sudo ./scripts/install.sh veins     # Veins + vanilla VASP build
sudo ./scripts/install.sh mirage    # MIRAGE overlay, rebuild
# or, all stages in one command:
sudo ./scripts/install.sh all
```

Install prefix is `/opt/mirage` (override with `MIRAGE_PREFIX=...`). Logs
are written to `/opt/mirage/logs/` per stage.

The final scenario tree lives at
`/opt/mirage/veins-5.2/src/vasp/scenario/`, which is the working
directory for all `./run` invocations.

---

## Reproduction expectations

- `scripts/install.sh all` completes with exit code 0 on a fresh
  Ubuntu 20.04 host; total wall-clock ≈ 10–25 minutes depending on CPU.
- `scripts/quick_test.sh` produces a detection log of at least a few
  thousand rows with several hundred `suspicious=1` entries. On the
  authors' Docker clean-room (Ubuntu 20.04, 16 vCPU), the 120 s
  simulation finishes in ≈ 53 s wall-clock with 327,868 rows and
  96,990 flagged.
- `scripts/run_single_seed.sh 0` completes all 18 configurations. Each
  config's `Calling finish()` line appears in the per-config log at
  `/tmp/mirage_run_single_<cfg>_seed0.log`.
- `scripts/verify_results.py --all --seeds 0 1 2 3 4` exits 0 if every
  claim in `CLAIMS.md` falls within its tolerance.

Exact numerical claims and their tolerances are documented in
[`CLAIMS.md`](CLAIMS.md); reference figures are in
[`reference_results/`](reference_results/).

---

## Troubleshooting

**"source setenv" fails in CI or subshell.** The install pipeline
already avoids OMNeT++'s `source setenv`. If you invoke OMNeT++ tools
directly, use the installed profile script instead:

```bash
source /etc/profile.d/mirage-omnetpp.sh
source /etc/profile.d/mirage-sumo.sh
export LD_LIBRARY_PATH="/opt/mirage/veins-5.2/out/gcc-release/src:$LD_LIBRARY_PATH"
```

**`sumo-launchd.py script is deprecated` warning / peer-shutdown.**
We intentionally use `bin/veins_launchd`, the modern replacement shipped
with Veins 5.2. `quick_test.sh` and `run_single_seed.sh` start it
automatically on port 9999.

**SIGSEGV at "Event #0".** This was caused by a duplicate
`ProposedIDMDetector.cc/.h` file triggering an ODR violation on GCC.
The duplicate has been removed from the repository; if you see this
symptom, your working tree may be out of date — `git pull` and rebuild.

**Port 9999 in use.** A previous `veins_launchd` instance may have
survived; `pkill -f veins_launchd` clears it.

**Route files `highway_seed{0..4}.rou.xml` missing.**
`run_single_seed.sh` auto-generates them via `generate_route_variants.py`
on first use; you can also run that script manually from the scenario
directory.

**`verify_results.py` reports "no detlog-*.csv found".** Make sure you
have run `run_single_seed.sh` or `run_multi_seed.sh` first; the
detection logs live at `/opt/mirage/veins-5.2/src/vasp/scenario/results/
detlog-<config>-<seed>-<timestamp>-<pid>.csv`. Set
`MIRAGE_RESULTS=/your/path` if you moved them.

---

## Citation

```bibtex
@inproceedings{mirage2026,
  title     = {MIRAGE: Detecting Fake Emergency Electronic Brake Light
               Attacks in V2X Networks via Event-Gated Behavioral Analysis},
  author    = {Anonymous},
  booktitle = {Proceedings of the 3rd ISOC Symposium on Vehicle Security
               and Privacy (VehicleSec '26)},
  year      = {2026}
}
```

(Update the `author` and page numbers after de-anonymization.)

## License and acknowledgments

MIT License (consistent with the upstream VASP project). See
[`LICENSE`](LICENSE).

Built on top of:

- [VASP](https://github.com/quic/vasp) by Qualcomm Innovation Center
- [Veins](https://veins.car2x.org/) by Christoph Sommer *et al.*
- [SUMO](https://sumo.dlr.de/) by the German Aerospace Center (DLR)
- [OMNeT++](https://omnetpp.org/) by András Varga / OpenSim Ltd.

Supported by USDOT TraCR (Grant 11543).
