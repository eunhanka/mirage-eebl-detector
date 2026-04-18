# Reference Results

Pre-computed artifacts from the original 5-seed run reported in the paper.
These materials let reviewers compare their re-run against the submitted
numbers without having to execute all 90 simulation runs themselves.

## Contents

### `figures/` — Paper figures (identical to the submission)

| File | Paper location | What it shows |
|---|---|---|
| `fig2_roc.png`, `.pdf` | §7.1 Fig. 2 | ROC curves for each detector |
| `fig3_per_attack.png`, `.pdf` | §7.3 Fig. 5 | Per-attack TPR bar chart |
| `fig5_sensitivity.png`, `.pdf` | §7.4 Fig. 6 | F1/TPR/FPR vs threshold Θ |
| `fig_ablation.png`, `.pdf` | §7.6 | Ablation study |
| `fig_mitigation.png`, `.pdf` | §7.5 | Deceleration reduction by IDM mitigation |

### `tables/` — LaTeX source of paper tables

| File | Paper location | Contents |
|---|---|---|
| `tab_comparison.tex` | §7.2 Table 4 | Aggregate TPR/FPR/Precision/F1 per detector |
| `tab_ablation.tex` | §7.6 | MIRAGE ablation study |
| `tab_latency.tex` | §8 | Detection latency per attack |
| `tab_mitigation.tex` | §7.5 | Deceleration severity with / without mitigation |

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
  large for git and have been archived separately — the DOI is listed in
  the main `README.md`. Re-running `run_multi_seed.sh` regenerates them.
- **OMNeT++ `.vec` / `.sca` scalar files** (~5.7 GB total). Archived on
  the same Zenodo DOI.

## Provenance

| Item | Value |
|---|---|
| Original run date | 2026-02-24 |
| Host CPU | (as in paper §6, footnote) |
| Compiler | Clang 14 (host) — note: our final install pipeline uses GCC 9.4 |
| OMNeT++ | 5.6.2 |
| SUMO | 1.8.0 |
| Veins | 5.2 (commit `c5b4d7c4`) |
| VASP | `0ec4af3` |

See `CLAIMS.md` in the repo root for the exact numerical values the paper
reports and the tolerances expected for re-execution on a different host.
