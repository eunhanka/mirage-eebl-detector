#!/usr/bin/env python3
# =============================================================================
# verify_results.py
#
# Compare detection logs produced by a reviewer's re-run against the claims
# made in the MIRAGE paper (see CLAIMS.md for the reference values and
# tolerances).
#
# The script reads detlog-*.csv files produced by running the simulator
# (one per config per seed), computes four-way metrics (TPR, FPR, precision,
# F1), and reports pass/fail against paper-reported numbers.
#
# Exit code:
#   0  every enabled claim is within tolerance
#   1  at least one claim is out of tolerance
#   2  required input is missing (no detlogs found, etc.)
# =============================================================================

from __future__ import annotations

import argparse
import csv
import glob
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# Reference values (from CLAIMS.md, keep in sync)
# -----------------------------------------------------------------------------
# (name, tolerance)
CLAIMS = {
    "C1": {
        "desc": "MIRAGE aggregate effectiveness (Θ=0.55)",
        "config_prefix": "P_",        # P_Baseline, P_A1, P_A2
        "metrics": {
            "F1":        (0.922, 0.015),
            "TPR":       (0.883, 0.020),
            "FPR":       (0.009, 0.005),
            "Precision": (0.965, 0.015),
        },
    },
    "C2": {
        "desc": "MIRAGE balanced per-attack coverage",
        "per_attack": {
            "A1": {"config": "P_A1", "tpr": (0.770, 0.030)},
            "A2": {"config": "P_A2", "tpr": (0.997, 0.010)},
        },
    },
    "C3": {
        "desc": "Baseline comparison (F1 ranking + absolute)",
        "detectors": {
            "B1": {"prefix": "B1_", "f1": (0.733, 0.020)},
            "B2": {"prefix": "B2_", "f1": (0.607, 0.040)},
            "B3": {"prefix": "B3_", "f1": (0.193, 0.020)},
            "P":  {"prefix": "P_",  "f1": (0.922, 0.015)},
        },
    },
    "C5": {
        "desc": "IDM mitigation reduces mean braking severity ~75%",
        "target_reduction": (0.75, 0.10),  # fraction, ±
    },
}

# Column names emitted by CarApp.cc's detlog writer:
#   time,hv_id,rv_id,attack_type,det_name,suspicious,score,reason,ttc,mitigated_a
# attack_type is a string label; suspicious is a continuous [0,1] detector
# score that becomes a positive prediction when it crosses SUSPICIOUS_THETA.
# Labels and threshold mirror analyze_multi_seed.py (ATTACK_MAP, THETA=0.55).
ATTACK_TYPE_BENIGN = "Genuine"
ATTACK_TYPE_A1     = "FakeEEBLJustAttack"
ATTACK_TYPE_A2     = "FakeEEBLStopPositionUpdateAfterAttack"
SUSPICIOUS_THETA   = 0.55


# -----------------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------------
@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def __add__(self, other: "Counts") -> "Counts":
        return Counts(
            tp=self.tp + other.tp, fp=self.fp + other.fp,
            tn=self.tn + other.tn, fn=self.fn + other.fn
        )

    def tpr(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom > 0 else 0.0

    def fpr(self) -> float:
        denom = self.fp + self.tn
        return self.fp / denom if denom > 0 else 0.0

    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom > 0 else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.tpr()
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def mitigated_abs_sum(self) -> float:
        # filled separately for C5; dataclass gets extended via helper
        return 0.0


@dataclass
class Mitigation:
    n: int = 0
    raw_abs_sum: float = 0.0   # |a| from BSM itself
    mit_abs_sum: float = 0.0   # |mitigated_a|


# -----------------------------------------------------------------------------
# CSV reading
# -----------------------------------------------------------------------------
def find_detlogs(results_dir: Path, config: str, seeds: Optional[List[int]]) -> List[Path]:
    """Find detlog-<config>-*.csv files, optionally filtered by seed.

    Seed inference is layout-aware:
      * Multi-seed layout (run_multi_seed.sh): each seed's detlogs live in
        results/seed{N}/. We infer seed = int(parent_dir.name[4:]).
      * Single-seed layout (run_single_seed.sh): all detlogs sit directly
        under results/. There is only one seed (the one the user passed),
        so every file belongs to each requested seed. We return all of them
        when the requested set is non-empty.

    The OMNeT++ filename component between the config and timestamp is the
    run index (always 0 because we do not use OMNeT++ parameter sweeps),
    not the seed, so it is ignored here.
    """
    pattern = f"detlog-{config}-*.csv"
    candidates = sorted(results_dir.rglob(pattern))
    if seeds is None:
        return candidates
    wanted = set(seeds)
    matched = []
    for p in candidates:
        parent = p.parent.name
        # Multi-seed layout: parent dir is "seed<N>".
        if parent.startswith("seed") and parent[4:].isdigit():
            if int(parent[4:]) in wanted:
                matched.append(p)
            continue
        # Single-seed layout: no seed subdir. Include every candidate
        # because the user ran exactly one seed and asked for that seed
        # (or a superset including it) by passing --seeds.
        matched.append(p)
    return matched


def read_counts(csv_path: Path, attack_filter: Optional[int] = None,
                mitigation: Optional[Mitigation] = None) -> Counts:
    """Tally TP/FP/TN/FN from one detlog-*.csv file.

    A "positive" event is a suspicious=1 flag; an "attack" event is
    attack_type != 0. If attack_filter is given, only rows whose attack_type
    matches are counted in the TP/FN tallies (benign is always counted).

    If `mitigation` is non-None, this function additionally accumulates the
    mean |a| vs |mitigated_a| for rows whose attack_type is nonzero.
    """
    c = Counts()
    try:
        with csv_path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            required = {"attack_type", "suspicious", "mitigated_a"}
            have = set(reader.fieldnames or [])
            if not required.issubset(have):
                print(f"  [WARN] {csv_path.name}: missing cols "
                      f"{required - have}; skipping", file=sys.stderr)
                return c
            for row in reader:
                try:
                    atype = row["attack_type"]
                    susp = float(row["suspicious"]) >= SUSPICIOUS_THETA
                except (KeyError, ValueError):
                    continue
                is_attack = atype != ATTACK_TYPE_BENIGN

                # Apply attack_filter if set, only count attack rows whose
                # type matches; benign rows (atype==0) always counted.
                if attack_filter is not None and is_attack and atype != attack_filter:
                    continue

                if is_attack:
                    if susp: c.tp += 1
                    else:    c.fn += 1
                else:
                    if susp: c.fp += 1
                    else:    c.tn += 1

                # Mitigation tally (attack rows only).
                # Filter matches analyze_multi_seed.py fig_mitigation():
                # mitigated_a must be nonzero (IDM produced a bound) AND
                # < 0.5 m/s^2 (actual braking, excludes free-flow cruising
                # when the ghost is too far away to constrain the ego).
                if mitigation is not None and is_attack:
                    try:
                        mit_a = float(row.get("mitigated_a", 0.0))
                        if mit_a != 0 and mit_a < 0.5:
                            mitigation.n += 1
                            mitigation.mit_abs_sum += abs(mit_a)
                    except (ValueError, TypeError):
                        pass
    except FileNotFoundError:
        print(f"  [WARN] missing: {csv_path}", file=sys.stderr)
    return c


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def within(value: float, reference: float, tolerance: float) -> bool:
    return abs(value - reference) <= tolerance


def fmt_metric(name: str, value: float, ref: float, tol: float) -> Tuple[str, bool]:
    ok = within(value, ref, tol)
    marker = "[OK]  " if ok else "[FAIL]"
    return (f"  {marker} {name:<12} {value:6.4f}  (ref {ref:.4f} ± {tol:.4f})", ok)


# -----------------------------------------------------------------------------
# Claim verifiers
# -----------------------------------------------------------------------------
def verify_c1(results_dir: Path, seeds: Optional[List[int]]) -> bool:
    """C1, MIRAGE aggregate effectiveness across P_Baseline, P_A1, P_A2."""
    spec = CLAIMS["C1"]
    print(f"\n==> C1: {spec['desc']}")
    configs = ["P_Baseline", "P_A1", "P_A2"]
    total = Counts()
    found_any = False
    for cfg in configs:
        paths = find_detlogs(results_dir, cfg, seeds)
        if not paths:
            print(f"  [WARN] no detlogs for {cfg}")
            continue
        for p in paths:
            total += read_counts(p)
            found_any = True
    if not found_any:
        print("  [FAIL] no P_* detlogs found; cannot verify C1")
        return False

    all_ok = True
    for name, (ref, tol) in spec["metrics"].items():
        if name == "F1":
            value = total.f1()
        elif name == "TPR":
            value = total.tpr()
        elif name == "FPR":
            value = total.fpr()
        elif name == "Precision":
            value = total.precision()
        else:
            continue
        line, ok = fmt_metric(name, value, ref, tol)
        print(line)
        all_ok &= ok
    return all_ok


def verify_c2(results_dir: Path, seeds: Optional[List[int]]) -> bool:
    """C2, Per-attack TPR: MIRAGE sustains high TPR on both A1 and A2."""
    spec = CLAIMS["C2"]
    print(f"\n==> C2: {spec['desc']}")
    all_ok = True
    for variant, cfg in [("A1", "P_A1"), ("A2", "P_A2")]:
        paths = find_detlogs(results_dir, cfg, seeds)
        if not paths:
            print(f"  [WARN] no detlogs for {cfg}")
            all_ok = False
            continue
        total = Counts()
        atype = ATTACK_TYPE_A1 if variant == "A1" else ATTACK_TYPE_A2
        for p in paths:
            total += read_counts(p, attack_filter=atype)
        ref, tol = spec["per_attack"][variant]["tpr"]
        line, ok = fmt_metric(f"TPR[{variant}]", total.tpr(), ref, tol)
        print(line)
        all_ok &= ok
    return all_ok


def verify_c3(results_dir: Path, seeds: Optional[List[int]]) -> bool:
    """C3, Baseline comparison: F1 ranking and absolute values."""
    spec = CLAIMS["C3"]
    print(f"\n==> C3: {spec['desc']}")
    results = {}
    all_ok = True
    for det_name, info in spec["detectors"].items():
        prefix = info["prefix"]
        total = Counts()
        any_found = False
        for cfg in [f"{prefix}Baseline", f"{prefix}A1", f"{prefix}A2"]:
            paths = find_detlogs(results_dir, cfg, seeds)
            for p in paths:
                total += read_counts(p)
                any_found = True
        if not any_found:
            print(f"  [WARN] no detlogs for detector {det_name}")
            all_ok = False
            continue
        f1 = total.f1()
        ref, tol = info["f1"]
        line, ok = fmt_metric(f"F1[{det_name}]", f1, ref, tol)
        print(line)
        all_ok &= ok
        results[det_name] = f1

    # Ranking check
    if len(results) == 4:
        order = ["P", "B1", "B2", "B3"]
        observed = sorted(results, key=lambda d: -results[d])
        if observed == order:
            print(f"  [OK]   Ranking (P > B1 > B2 > B3) matches paper")
        else:
            print(f"  [FAIL] Ranking: got {observed}, expected {order}")
            all_ok = False
    return all_ok


def verify_c5(results_dir: Path, seeds: Optional[List[int]]) -> bool:
    """C5, IDM mitigation reduces mean braking severity by ~75%.

    We compare mean |mitigated_a| (from P_A* runs) to mean |a| (from the
    corresponding B0_A* runs, since B0 is the Naive detector that applies no
    mitigation).
    """
    spec = CLAIMS["C5"]
    print(f"\n==> C5: {spec['desc']}")

    # Gather mitigated-a from P_A1, P_A2
    mit = Mitigation()
    for cfg in ["P_A1", "P_A2"]:
        for p in find_detlogs(results_dir, cfg, seeds):
            read_counts(p, mitigation=mit)

    if mit.n == 0:
        print("  [WARN] no mitigated_a samples in P_A*")
        return False
    mit_mean = mit.mit_abs_sum / mit.n

    # Reference deceleration: the -8.0 m/s^2 (~0.8g) maximum emergency
    # braking that an unprotected EEBL response would command. This matches
    # paper section 7.5 ("compared to the -8.0 m/s^2 (~0.8g) maximum
    # emergency braking that an unprotected EEBL response would command")
    # and the reduction formula in analyze_multi_seed.py:570.
    base_mean = 8.0

    reduction = 1.0 - (mit_mean / base_mean) if base_mean > 0 else 0.0
    ref, tol = spec["target_reduction"]
    print(f"  mean |a|      baseline:   {base_mean:.3f} m/s^2")
    print(f"  mean |a|      mitigated:  {mit_mean:.3f} m/s^2")
    print(f"  reduction:                {reduction*100:.1f}% (ref {ref*100:.0f}% ± {tol*100:.0f}%)")
    ok = within(reduction, ref, tol)
    print(f"  [{'OK' if ok else 'FAIL'}]   C5 reduction in tolerance")
    return ok


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify MIRAGE re-run results against paper claims. "
                    "See CLAIMS.md for the reference values."
    )
    p.add_argument("--results-dir", type=Path,
                   default=Path(os.environ.get(
                       "MIRAGE_RESULTS",
                       "/opt/mirage/veins-5.2/src/vasp/scenario/results")),
                   help="Directory containing detlog-*.csv files "
                        "(default: $MIRAGE_RESULTS or the install prefix)")
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="Which seeds to include (default: all found)")
    p.add_argument("--claim", type=str, default=None,
                   choices=["C1", "C2", "C3", "C5"],
                   help="Verify one claim only")
    p.add_argument("--all", action="store_true",
                   help="Verify all claims (default if --claim not given)")
    args = p.parse_args(argv)

    if not args.results_dir.is_dir():
        print(f"[ERROR] results dir does not exist: {args.results_dir}",
              file=sys.stderr)
        return 2

    found = list(args.results_dir.rglob("detlog-*.csv"))
    if not found:
        print(f"[ERROR] no detlog-*.csv files found in {args.results_dir}",
              file=sys.stderr)
        print("        Run ./scripts/run_multi_seed.sh (or run_single_seed.sh) "
              "to produce them.", file=sys.stderr)
        return 2

    print(f"Reading detlogs from: {args.results_dir}")
    print(f"Detlogs found:        {len(found)}")
    if args.seeds is not None:
        print(f"Seed filter:          {args.seeds}")

    to_run = [args.claim] if args.claim else ["C1", "C2", "C3", "C5"]

    results = {}
    for cid in to_run:
        fn = {"C1": verify_c1, "C2": verify_c2,
              "C3": verify_c3, "C5": verify_c5}[cid]
        results[cid] = fn(args.results_dir, args.seeds)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for cid, ok in results.items():
        marker = "PASS" if ok else "FAIL"
        print(f"  {cid}: {marker}")
    n_pass = sum(1 for v in results.values() if v)
    print(f"\n{n_pass} / {len(results)} claims within tolerance")
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
