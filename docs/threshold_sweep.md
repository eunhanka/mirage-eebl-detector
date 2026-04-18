# Threshold Sensitivity Sweep (Claim C4)

This document describes how to reproduce the threshold-sensitivity
analysis reported in paper section 7.4 (Figure 6). The sweep does
**not** require re-compilation or extra simulation runs: the detection
log already contains a continuous `score` column per BSM, so the
post-hoc Python pipeline can evaluate any target threshold Theta by
re-classifying (`score >= Theta`) without re-running the simulator.

## Summary of Claim C4

> Performance is stable across Theta in [0.45, 0.59]: TPR stays above
> 0.88 and F1 stays above 0.92 throughout this range.

Outside this band the paper reports a sharp transition: at Theta = 0.60,
TPR drops to roughly 0.41 and F1 to roughly 0.57 because Check 4's
weight (0.60) no longer exceeds the threshold on its own. At Theta
below 0.45, FPR rises past the acceptable EEBL budget.

## How the sweep works

The scenario's `detlog-*.csv` files record one row per received BSM with
the following structure:

```
time, hv_id, rv_id, attack_type, det_name, suspicious, score, reason, ttc, mitigated_a
```

The `score` column is the cumulative weighted anomaly score as computed
by MIRAGE at simulation time. It is saved as a floating point number
between 0 and 1 (before thresholding). The `suspicious` column is the
classification result at the compiled-in operating point (Theta = 0.55).

The analysis scripts in `src/vasp/scenario/` use `score` together with
`attack_type` to compute TPR/FPR/F1 at any Theta without recompilation:

```python
thresholds = np.linspace(0.05, 1.0, 80)
for t in thresholds:
    pred = (scores >= t).astype(int)
    # tp / fp / tn / fn from pred + ground-truth
```

This is the exact logic used to produce the paper's Figure 6.

## Recipe: Single-seed sweep (about 30 minutes wall-clock including install)

### 1. Run the single-seed protocol if you have not already

```bash
./scripts/run_single_seed.sh 0
```

This produces 18 detlog files at
`/opt/mirage/veins-5.2/src/vasp/scenario/results/detlog-*.csv`. The
P_Proposed detlogs in particular (`detlog-P_Baseline-*.csv`,
`detlog-P_A1-*.csv`, `detlog-P_A2-*.csv`) carry the `score` column
consumed by the sweep.

### 2. Run the sweep analysis

```bash
cd /opt/mirage/veins-5.2/src/vasp/scenario
python3 analyze_multi_seed.py results/
```

`analyze_multi_seed.py` works with any number of seeds. With a single
seed it produces a point estimate per Theta (no mean + std band); with
more than one seed it produces a mean with a shaded standard-deviation
band. Either way, output goes to:

```
results/figures/fig5_sensitivity.png
results/figures/fig5_sensitivity.pdf
```

### 3. Compare against the paper figure

The ground-truth reference is committed at
`reference_results/figures/fig5_sensitivity.png`. Qualitative
agreement criteria:

- F1 curve is flat (>= 0.92) across Theta in [0.45, 0.59].
- Green shaded band marks this stable region on the x-axis.
- F1 drops sharply around Theta = 0.60 (Check 4's weight boundary).
- TPR and FPR decrease monotonically as Theta rises; TPR stays >= 0.88
  inside the stable region.
- The red star marks the best-F1 Theta; it should sit inside the
  shaded region (paper places it at Theta = 0.52, F1 ~= 0.925).

Exact pixel agreement is not expected because of matplotlib version
drift and, for multi-seed runs, seed-specific variance. The shape and
the plateau-then-drop pattern are what matters.

## Recipe: Full 5-seed sweep (about 90 minutes wall-clock)

```bash
cd /opt/mirage/veins-5.2/src/vasp/scenario
./run_multi_seed.sh 0 1 2 3 4     # ~1 hour
python3 analyze_multi_seed.py results/
```

The 5-seed version adds a shaded mean +/- std band around each curve,
which tightens the visual comparison to the paper figure.

## Why no recompilation is needed

- MIRAGE scores each BSM using the full weighted sum of failed checks
  and writes the raw score to the detlog.
- The threshold Theta is applied only when forming the `suspicious`
  flag in the detlog, but the raw score is preserved untouched.
- Every Theta evaluation in the sensitivity sweep is a simple pandas
  comparison against the stored score, carried out entirely offline.

This is a deliberate design choice that makes C4 reviewer-cheap: one
simulation run answers every Theta question in Figure 6.

## Relationship to the operating-point choice (Theta = 0.55)

The operating point Theta = 0.55 is hard-coded as a `constexpr` in
`src/vasp/mdm/MisbehaviorDetectors.h` because it affects which BSMs
get routed through the IDM mitigation layer in real time. Changing
this constant would alter the `suspicious` labels and the downstream
mitigation behavior, but it would not change the Theta sweep figure,
which always spans the full range [0.05, 1.0] regardless of the
compiled-in operating point.

Reviewers who want to explore a different compiled-in operating point
(for example, to check whether the mitigation layer behaves correctly
at Theta = 0.50 or 0.60) may edit the constant, rebuild
(`make -j$(nproc) MODE=release`), and re-run. This is not required to
validate C4 and is not scored by `verify_results.py`.
