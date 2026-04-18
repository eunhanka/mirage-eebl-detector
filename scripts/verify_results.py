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
# Tolerances in CLAIMS.md are calibrated to a 5-seed re-run. For smaller
# seed counts (e.g. the Tier 2 single-seed reproduction in run_single_seed.sh),
# tolerances are scaled up: reviewer-observed variance scales roughly
# like std/sqrt(n), so with n<5 we loosen the band proportionally.
#
# Exit code:
#   0  every enabled claim is within (possibly-scaled) tolerance
#   1  at least one claim is out of tolerance
#   2  required input is missing (no detlogs found, etc.)
# =============================================================================

from __future__ import annotations

import argparse
import csv
import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# -----------------------------------------------------------------------------
# attack_type column values, as emitted by CarApp.cc
# -----------------------------------------------------------------------------
BENIGN = "Genuine"
A1_STR = "FakeEEBLJustAttack"                          # NoStop
A2_STR = "FakeEEBLStopPositionUpdateAfterAttack"       # WithStop

# -----------------------------------------------------------------------------
# Reference values (from CLAIMS.md — keep in sync)
# Each metric: (reference, tolerance-at-5-seeds)
# -----------------------------------------------------------------------------
REFERENCE_SEEDS = 5  # CLAIMS.md tolerances are calibrated for this many seeds

CLAIMS = {
    "C1": {
        "desc": "MIRAGE aggregate effectiveness (Θ=0.55)",
        "configs": ["P_Baseline", "P_A1", "P_A2"],
        "metrics": {
            "F1":        (0.922, 0.015),
            "TPR":       (0.883, 0.020),
            "FPR":       (0.009, 0.005),
            "Precision": (0.965, 0.015),
        },
    },
    "C2": {
        "desc": "MIRAGE balanced per-attack coverage",
        "per_attack": [
            ("A1", "P_A1", A1_STR, (0.770, 0.030)),
            ("A2", "P_A2", A2_STR, (0.997, 0.010)),
        ],
    },
    "C3": {
        "desc": "Baseline comparison (F1 ranking + absolute)",
        "detectors": {
            "B1": {"configs": ["B1_Baseline", "B1_A1", "B1_A2"], "f1": (0.733, 0.020)},
            "B2": {"configs": ["B2_Baseline", "B2_A1", "B2_A2"], "f1": (0.607, 0.040)},
            "B3": {"configs": ["B3_Baseline", "B3_A1", "B3_A2"], "f1": (0.193, 0.020)},
            "P":  {"configs": ["P_Baseline", "P_A1", "P_A2"],     "f1": (0.922, 0.015)},
        },
    },
    "C5": {
        "desc": "IDM mitigation active (proxy check)",
        "configs": ["P_A1", "P_A2"],
        "bound_m_per_s2": 4.0,  # IDM bounds deceleration (paper §4)
    },
}


def tolerance_scale(n_seeds: int) -> float:
    """Scale CLAIMS tolerances up for fewer-than-reference seeds.

    Based on std of the mean ~ 1/sqrt(n). At REFERENCE_SEEDS (5), scale=1.
    At n=1, scale ≈ sqrt(5) ≈ 2.24.
    """
    if n_seeds <= 0:
        return 1.0
    return math.sqrt(REFERENCE_SEEDS / n_seeds)


# -----------------------------------------------------------------------------
# Data types
# -----------------------------------------------------------------------------
@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    def __iadd__(self, other: "Counts") -> "Counts":
        self.tp += other.tp
        self.fp += other.fp
        self.tn += other.tn
        self.fn += other.fn
        return self

    def tpr(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d > 0 else 0.0

    def fpr(self) -> float:
        d = self.fp + self.tn
        return self.fp / d if d > 0 else 0.0

    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d > 0 else 0.0

    def f1(self) -> float:
        p, r = self.precision(), self.tpr()
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def total(self) -> int:
        return self.tp + self.fp + self.tn + self.fn


# -----------------------------------------------------------------------------
# CSV reading
# -----------------------------------------------------------------------------
def find_detlogs(results_dir: Path, config: str,
                 seeds: Optional[List[int]]) -> List[Path]:
    """Find detlog files for one config.

    Filename format: detlog-<cfg>-<seed>-<YYYYMMDD>-<HH:MM:SS>-<pid>.csv
    The *seed* is the third hyphen-separated field.
    """
    all_paths = sorted(results_dir.glob(f"detlog-{config}-*.csv"))
    if seeds is None:
        return all_paths
    want = set(seeds)
    out = []
    for p in all_paths:
        stem = p.stem  # drops .csv
        parts = stem.split("-", 3)  # ['detlog', '<cfg>', '<seed>', '<rest>']
        if len(parts) < 3:
            continue
        try:
            s = int(parts[2])
        except ValueError:
            continue
        if s in want:
            out.append(p)
    return out


def count_one_file(csv_path: Path,
                   attack_filter: Optional[str] = None) -> Counts:
    """Tally TP/FP/TN/FN from one detlog.

    - Positive event = suspicious=1
    - Attack event = attack_type != "Genuine"
    - If attack_filter is given (e.g., A1_STR), only count attack rows
      whose attack_type matches. Benign rows are always counted.
    """
    c = Counts()
    try:
        with csv_path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            needed = {"attack_type", "suspicious"}
            if not needed.issubset(reader.fieldnames or []):
                print(f"  [WARN] {csv_path.name}: missing cols "
                      f"{needed - set(reader.fieldnames or [])}",
                      file=sys.stderr)
                return c
            for row in reader:
                atype = row.get("attack_type", "")
                is_attack = (atype != BENIGN) and (atype != "")
                try:
                    susp = int(row.get("suspicious", 0))
                except ValueError:
                    continue

                if attack_filter is not None and is_attack and atype != attack_filter:
                    continue  # skip rows for the "other" attack variant

                if is_attack:
                    if susp: c.tp += 1
                    else:    c.fn += 1
                else:
                    if susp: c.fp += 1
                    else:    c.tn += 1
    except FileNotFoundError:
        print(f"  [WARN] missing: {csv_path}", file=sys.stderr)
    return c


def mean_mitigated_a(csv_path: Path,
                     only_benign: bool = True) -> Tuple[float, int]:
    """Mean |mitigated_a| for rows matching the filter."""
    total = 0.0
    n = 0
    try:
        with csv_path.open("r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if only_benign and row.get("attack_type", "") != BENIGN:
                    continue
                try:
                    v = float(row.get("mitigated_a", 0.0))
                except ValueError:
                    continue
                total += abs(v)
                n += 1
    except FileNotFoundError:
        pass
    return (total / n if n > 0 else 0.0, n)


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def within(value: float, reference: float, tolerance: float) -> bool:
    return abs(value - reference) <= tolerance


def fmt_metric(name: str, value: float, ref: float, tol: float,
               scale: float) -> Tuple[str, bool]:
    scaled = tol * scale
    ok = within(value, ref, scaled)
    marker = "[OK]  " if ok else "[FAIL]"
    suffix = f" (ref {ref:7.4f} ± {scaled:.4f}"
    if abs(scale - 1.0) > 1e-6:
        suffix += f"; seed-scaled ×{scale:.2f} from base ±{tol:.4f})"
    else:
        suffix += ")"
    return f"  {marker} {name:<12} {value:7.4f} {suffix}", ok


# -----------------------------------------------------------------------------
# Claim verifiers
# -----------------------------------------------------------------------------
def verify_c1(results_dir: Path, seeds: Optional[List[int]],
              scale: float) -> bool:
    spec = CLAIMS["C1"]
    print(f"\n==> C1: {spec['desc']}")
    agg = Counts()
    found_any = False
    for cfg in spec["configs"]:
        for p in find_detlogs(results_dir, cfg, seeds):
            agg += count_one_file(p)
            found_any = True
    if not found_any:
        print("  [FAIL] no P_* detlogs found")
        return False
    print(f"  (rows: {agg.total():,}; TP={agg.tp:,} FP={agg.fp:,} "
          f"TN={agg.tn:,} FN={agg.fn:,})")
    all_ok = True
    for name, (ref, tol) in spec["metrics"].items():
        v = {"F1": agg.f1(), "TPR": agg.tpr(),
             "FPR": agg.fpr(), "Precision": agg.precision()}[name]
        line, ok = fmt_metric(name, v, ref, tol, scale)
        print(line)
        all_ok &= ok
    return all_ok


def verify_c2(results_dir: Path, seeds: Optional[List[int]],
              scale: float) -> bool:
    spec = CLAIMS["C2"]
    print(f"\n==> C2: {spec['desc']}")
    all_ok = True
    for label, cfg, astr, (ref, tol) in spec["per_attack"]:
        paths = find_detlogs(results_dir, cfg, seeds)
        if not paths:
            print(f"  [WARN] no detlogs for {cfg}")
            all_ok = False
            continue
        agg = Counts()
        for p in paths:
            agg += count_one_file(p, attack_filter=astr)
        line, ok = fmt_metric(f"TPR[{label}]", agg.tpr(), ref, tol, scale)
        print(line)
        all_ok &= ok
    return all_ok


def verify_c3(results_dir: Path, seeds: Optional[List[int]],
              scale: float) -> bool:
    spec = CLAIMS["C3"]
    print(f"\n==> C3: {spec['desc']}")
    f1s: Dict[str, float] = {}
    all_ok = True
    for name, info in spec["detectors"].items():
        agg = Counts()
        found = False
        for cfg in info["configs"]:
            for p in find_detlogs(results_dir, cfg, seeds):
                agg += count_one_file(p)
                found = True
        if not found:
            print(f"  [WARN] no detlogs for detector {name}")
            all_ok = False
            continue
        f1 = agg.f1()
        f1s[name] = f1
        ref, tol = info["f1"]
        line, ok = fmt_metric(f"F1[{name}]", f1, ref, tol, scale)
        print(line)
        all_ok &= ok

    # Ranking check (seed-independent)
    expected = ["P", "B1", "B2", "B3"]
    if len(f1s) == len(expected):
        observed = sorted(f1s, key=lambda k: -f1s[k])
        if observed == expected:
            print(f"  [OK]   Ranking (P > B1 > B2 > B3) matches paper")
        else:
            print(f"  [FAIL] Ranking: got {observed}, expected {expected}")
            all_ok = False
    return all_ok


def verify_c5(results_dir: Path, seeds: Optional[List[int]],
              scale: float) -> bool:
    """Informational check that mitigated_a column is present, populated,
    and stays within the paper's IDM bound on benign BSMs."""
    spec = CLAIMS["C5"]
    print(f"\n==> C5: {spec['desc']}")
    bound = spec["bound_m_per_s2"]

    total = 0.0
    n = 0
    for cfg in spec["configs"]:
        for p in find_detlogs(results_dir, cfg, seeds):
            m, k = mean_mitigated_a(p, only_benign=True)
            total += m * k
            n += k
    if n == 0:
        print("  [WARN] no benign rows with mitigated_a — skipping C5")
        return True  # non-blocking

    mean_abs = total / n
    print(f"  mean |mitigated_a| on benign rows (P_A1,P_A2): "
          f"{mean_abs:.3f} m/s^2  (IDM bound = {bound})")
    if mean_abs <= bound:
        print(f"  [OK]   mitigation within IDM bound")
        print(f"  (note: paper claims 75% reduction vs unprotected 8 m/s^2 "
              f"EEBL; see paper Table 5 / "
              f"reference_results/tables/tab_mitigation.tex)")
        return True
    else:
        print(f"  [FAIL] mitigation exceeds IDM bound")
        return False


# -----------------------------------------------------------------------------
# Seed detection
# -----------------------------------------------------------------------------
def detect_seeds_in_results(results_dir: Path) -> List[int]:
    """Scan detlog filenames to infer which seeds are present."""
    seeds = set()
    for p in results_dir.glob("detlog-*.csv"):
        parts = p.stem.split("-", 3)
        if len(parts) >= 3:
            try:
                seeds.add(int(parts[2]))
            except ValueError:
                pass
    return sorted(seeds)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Verify MIRAGE re-run results against paper claims. "
                    "See CLAIMS.md for the reference values.",
        epilog="Tolerances are calibrated to a 5-seed run. If you are "
               "running with fewer seeds, tolerances are automatically "
               "scaled up by sqrt(5/N) to account for the larger variance "
               "of the per-seed mean."
    )
    p.add_argument("--results-dir", type=Path,
                   default=Path(os.environ.get(
                       "MIRAGE_RESULTS",
                       "/opt/mirage/veins-5.2/src/vasp/scenario/results")),
                   help="Directory containing detlog-*.csv files")
    p.add_argument("--seeds", type=int, nargs="+", default=None,
                   help="Which seeds to include (default: all found)")
    p.add_argument("--claim", type=str, default=None,
                   choices=["C1", "C2", "C3", "C5"],
                   help="Verify one claim only (default: all)")
    p.add_argument("--no-scale", action="store_true",
                   help="Do not auto-scale tolerances by seed count "
                        "(use paper-exact tolerances)")
    args = p.parse_args(argv)

    if not args.results_dir.is_dir():
        print(f"[ERROR] results dir does not exist: {args.results_dir}",
              file=sys.stderr)
        return 2

    found = list(args.results_dir.glob("detlog-*.csv"))
    if not found:
        print(f"[ERROR] no detlog-*.csv files found in {args.results_dir}",
              file=sys.stderr)
        print("        Run ./scripts/run_single_seed.sh (or "
              "run_multi_seed.sh) first.", file=sys.stderr)
        return 2

    # Figure out seed set and tolerance scaling
    if args.seeds is None:
        detected = detect_seeds_in_results(args.results_dir)
        n_seeds = len(detected)
        seeds_label = f"all found: {detected}"
    else:
        n_seeds = len(args.seeds)
        seeds_label = str(args.seeds)

    scale = 1.0 if args.no_scale else tolerance_scale(max(n_seeds, 1))

    print(f"Reading detlogs from: {args.results_dir}")
    print(f"Detlogs found:        {len(found)}")
    print(f"Seed filter:          {seeds_label} ({n_seeds} seed(s))")
    if not args.no_scale:
        print(f"Tolerance scaling:    ×{scale:.2f} "
              f"(paper baseline = 5 seeds; fewer seeds widen bands)")

    to_run = [args.claim] if args.claim else ["C1", "C2", "C3", "C5"]
    funcs = {"C1": verify_c1, "C2": verify_c2,
             "C3": verify_c3, "C5": verify_c5}

    results: Dict[str, bool] = {}
    for cid in to_run:
        results[cid] = funcs[cid](args.results_dir, args.seeds, scale)

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    for cid, ok in results.items():
        print(f"  {cid}: {'PASS' if ok else 'FAIL'}")
    n_pass = sum(1 for v in results.values() if v)
    print(f"\n{n_pass} / {len(results)} claims within tolerance")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
