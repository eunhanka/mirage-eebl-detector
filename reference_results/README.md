# Reference Results

Pre-computed artifacts from the original 5-seed run reported in the paper.
These materials let reviewers compare their re-run against the submitted
numbers without having to execute all 90 simulation runs themselves.

## Contents

### `figures/`: Paper figures (identical to the submission)

| File | Paper location | What it shows |
|---|---|---|
| `fig2_roc.png`, `.pdf` | Supplementary | ROC curves across detectors (not in paper; supports C1/C3) |
| `fig3_per_attack.png`, `.pdf` | Section 7, Fig. 5 | Per-attack TPR bar chart (supports C2) |
| `fig5_sensitivity.png`, `.pdf` | Section 7, Fig. 6 | F1/TPR/FPR vs threshold Θ (supports C4) |
| `fig_ablation.png`, `.pdf` | Section 7, Fig. 7 | Detection check ablation study |
| `fig_mitigation.png`, `.pdf` | Supplementary | Deceleration reduction by IDM mitigation (not in paper; paper Table 5 provides the tabular form; supports C5) |

### `tables/`: LaTeX source of paper tables

| File | Paper location | Contents |
|---|---|---|
| `tab_comparison.tex` | Section 7, Table 4 | Aggregate TPR/FPR/Precision/F1 per detector |
| `tab_ablation.tex` | Section 7 | MIRAGE ablation study |
| `tab_latency.tex` | Section 8 | Detection latency per attack |
| `tab_mitigation.tex` | Section 7, Table 5 | Deceleration severity with / without mitigation |

### Verifier outputs (from the clean-room v3 run, Zenodo-based)

| File | Contents |
|---|---|
| `verify_single_seed.txt` | Verbatim verifier output for `--seeds 0` (single-seed) |
| `verify_multi_seed.txt` | Verbatim verifier output for `--seeds 0 1 2 3 4` (five seeds, paper-matching) |
| `clean_room_summary.txt` | Stage-by-stage exit codes, wall-clock timings, and key metrics from the full clean-room verification |

Reviewers can diff their own runs against these files to confirm bit-identical verifier behavior on a matching platform.

## How to compare your re-run to these reference values

1. Execute the experiments:
   ```bash
   ./scripts/run_single_seed.sh 0      # ~10 min for all 18 configs, 1 seed
   # or for the full paper protocol:
   ./scripts/run_multi_seed.sh 0 1 2 3 4
   ```
2. Run the automated checker:
   ```bash
   ./scripts/verify_results.py --all --seeds 0 1 2 3 4
   ```
   The script reads the `detlog-*.csv` files just produced in
   `results/`, computes TPR / FPR / Precision / F1 per detector, and
   compares against the claims in `CLAIMS.md`.
3. Qualitatively compare your regenerated figures against the PNGs in
   `figures/`. They will not be pixel-identical (matplotlib version,
   stochastic traffic) but should show the same shape: MIRAGE's ROC
   dominates in the top-left, and Fig. 3 should show MIRAGE as the only
   bar above 0.7 for *both* A1 and A2.

## What is NOT in this directory

- **Raw per-run detlog CSVs** (5-seed × 18-config ≈ 1.8 GB). These were too
  large for git and have been archived separately. The Zenodo DOI is
  [10.5281/zenodo.19639252](https://doi.org/10.5281/zenodo.19639252).
  Re-running `run_multi_seed.sh` regenerates them locally.
- **OMNeT++ `.vec` / `.sca` scalar files** (~5.7 GB total). Archived on the
  same Zenodo DOI.

## Provenance

| Item | Value |
|---|---|
| Original run date | 2026-02-24 |
| Host CPU | (as in paper §6, footnote) |
| Compiler | Clang 14 (host), note: our final install pipeline uses GCC 9.4 |
| OMNeT++ | 5.6.2 |
| SUMO | 1.8.0 |
| Veins | 5.2 (commit `c5b4d7c4`) |
| VASP | `0ec4af3` |

See `CLAIMS.md` in the repo root for the exact numerical values the paper
reports and the tolerances expected for re-execution on a different host.
