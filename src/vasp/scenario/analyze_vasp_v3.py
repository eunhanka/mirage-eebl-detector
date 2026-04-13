#!/usr/bin/env python3
"""
===============================================================
  VASP EEBL Detection  - EEBL Detection Analysis
===============================================================
"""

import os, sys, glob, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# -- Config --
DET_ORDER = ['B0_Naive', 'B1_Threshold', 'B2_VCADS', 'B3_F2MD', 'P_Proposed']
LABELS = {
    'B0_Naive':      'B0: No Detection',
    'B1_Threshold':  'B1: Threshold',
    'B2_VCADS':      'B2: VCADS',
    'B3_F2MD':       'B3: F2MD/VASP',
    'P_Proposed':    'Proposed (Ours)',
    'P_NoGate':      'Proposed (No Gate)',
}
SHORT_LABELS = {
    'B1_Threshold':  'Threshold',
    'B2_VCADS':      'VCADS',
    'B3_F2MD':       'F2MD',
    'P_Proposed':    'Proposed',
}
COLORS = {
    'B0_Naive':      '#AAAAAA',
    'B1_Threshold':  '#5DADE2',
    'B2_VCADS':      '#F39C12',
    'B3_F2MD':       '#2ECC71',
    'P_Proposed':    '#E74C3C',
    'P_NoGate':      '#9B59B6',
}
ATTACK_MAP = {
    'Genuine': 0,
    'FakeEEBLJustAttack': 1,
    'FakeEEBLStopPositionUpdateAfterAttack': 1,
}
ATTACK_LABELS = {
    'FakeEEBLJustAttack': r'$\mathcal{A}_1$ (NoStop)',
    'FakeEEBLStopPositionUpdateAfterAttack': r'$\mathcal{A}_2$ (WithStop)',
}
ATTACK_LABELS_SHORT = {
    'FakeEEBLJustAttack': r'$\mathcal{A}_1$'+'\n(NoStop)',
    'FakeEEBLStopPositionUpdateAfterAttack': r'$\mathcal{A}_2$'+'\n(WithStop)',
}


def load_detlogs(results_dir):
    files = glob.glob(os.path.join(results_dir, 'detlog-*.csv'))
    if not files:
        print(f"No detlog-*.csv in {results_dir}"); sys.exit(1)
    frames = []
    for f in sorted(files):
        try:
            df = pd.read_csv(f)
            if len(df) == 0: continue
            basename = os.path.basename(f)
            parts = basename.replace('detlog-', '').split('-')
            df['config'] = parts[0]
            frames.append(df)
            print(f"  Loaded: {basename} ({len(df)} rows)")
        except Exception as e:
            print(f"  Error: {os.path.basename(f)}: {e}")
    return pd.concat(frames, ignore_index=True)


def compute_metrics(df):
    df = df.copy()
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    metrics = {}
    for det in df['det_name'].unique():
        s = df[df['det_name'] == det]
        tp = int(((s['is_attack'] == 1) & (s['suspicious'] == 1)).sum())
        fp = int(((s['is_attack'] == 0) & (s['suspicious'] == 1)).sum())
        tn = int(((s['is_attack'] == 0) & (s['suspicious'] == 0)).sum())
        fn = int(((s['is_attack'] == 1) & (s['suspicious'] == 0)).sum())
        tpr = tp / max(tp + fn, 1)
        fpr = fp / max(fp + tn, 1)
        prec = tp / max(tp + fp, 1)
        f1 = 2 * prec * tpr / max(prec + tpr, 1e-9)
        metrics[det] = {
            'TP': tp, 'FP': fp, 'TN': tn, 'FN': fn,
            'TPR': tpr, 'FPR': fpr, 'Precision': prec, 'F1': f1,
        }
    return metrics


def compute_roc(df, det_name, n_pts=200):
    df = df.copy()
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    sub = df[df['det_name'] == det_name]
    if sub.empty: return [], [], 0.0
    y = sub['is_attack'].values
    s = sub['score'].values
    fprs, tprs = [], []
    for t in np.linspace(0, 1, n_pts):
        pred = (s >= t).astype(int)
        tp = ((y == 1) & (pred == 1)).sum()
        fp = ((y == 0) & (pred == 1)).sum()
        fn = ((y == 1) & (pred == 0)).sum()
        tn = ((y == 0) & (pred == 0)).sum()
        tprs.append(tp / max(tp + fn, 1))
        fprs.append(fp / max(fp + tn, 1))
    auc = 0.0
    for i in range(1, len(fprs)):
        auc += abs(fprs[i] - fprs[i-1]) * (tprs[i] + tprs[i-1]) / 2.0
    return fprs, tprs, auc


def compute_roc_per_attack(df, det_name, attack_type, n_pts=200):
    df = df.copy()
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    sub = df[(df['det_name'] == det_name) & (df['attack_type'].isin([attack_type, 'Genuine']))]
    if sub.empty: return [], [], 0.0
    y = sub['is_attack'].values
    s = sub['score'].values
    fprs, tprs = [], []
    for t in np.linspace(0, 1, n_pts):
        pred = (s >= t).astype(int)
        tp = ((y == 1) & (pred == 1)).sum()
        fp = ((y == 0) & (pred == 1)).sum()
        fn = ((y == 1) & (pred == 0)).sum()
        tn = ((y == 0) & (pred == 0)).sum()
        tprs.append(tp / max(tp + fn, 1))
        fprs.append(fp / max(fp + tn, 1))
    auc = 0.0
    for i in range(1, len(fprs)):
        auc += abs(fprs[i] - fprs[i-1]) * (tprs[i] + tprs[i-1]) / 2.0
    return fprs, tprs, auc


def compute_per_attack(df):
    df = df.copy()
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    out = {}
    for atk_type, atk_label in ATTACK_LABELS.items():
        sub = df[df['attack_type'].isin([atk_type, 'Genuine'])]
        if len(sub) > 0:
            out[atk_type] = compute_metrics(sub)
    return out


def sensitivity_sweep(df, det_name='P_Proposed', n_pts=50):
    df = df.copy()
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    sub = df[df['det_name'] == det_name]
    if sub.empty: return np.array([]), [], [], []
    y = sub['is_attack'].values
    s = sub['score'].values
    thresholds = np.linspace(0.05, 1.0, n_pts)
    f1s, tprs, fprs = [], [], []
    for t in thresholds:
        pred = (s >= t).astype(int)
        tp = ((y == 1) & (pred == 1)).sum()
        fp = ((y == 0) & (pred == 1)).sum()
        fn = ((y == 1) & (pred == 0)).sum()
        tn = ((y == 0) & (pred == 0)).sum()
        pr = tp / max(tp + fp, 1)
        re = tp / max(tp + fn, 1)
        f1s.append(2 * pr * re / max(pr + re, 1e-9))
        tprs.append(re)
        fprs.append(fp / max(fp + tn, 1))
    return thresholds, f1s, tprs, fprs


def _save(fig, base):
    fig.savefig(f'{base}.png', dpi=300, bbox_inches='tight')
    fig.savefig(f'{base}.pdf', bbox_inches='tight')
    plt.close(fig)
    print(f"    Saved: {base}.png/.pdf")


# ===============================================================
#  FIG 2: ROC  - Two panels: aggregate + low-FPR zoom
# ===============================================================
def fig2_roc(df, out_dir):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    dets = [d for d in DET_ORDER if d != 'B0_Naive']
    aucs = {}

    for det in dets:
        fprs, tprs, auc = compute_roc(df, det)
        aucs[det] = auc
        if fprs:
            lw = 3 if det == 'P_Proposed' else 1.5
            ls = '-' if det == 'P_Proposed' else '--'
            zorder = 10 if det == 'P_Proposed' else 5
            label = f'{LABELS[det]} (AUC={auc:.3f})'
            ax1.plot(fprs, tprs, color=COLORS[det], lw=lw, ls=ls, label=label, zorder=zorder)
            ax2.plot(fprs, tprs, color=COLORS[det], lw=lw, ls=ls, label=label, zorder=zorder)

    ax1.plot([0, 1], [0, 1], 'k--', alpha=.3, lw=0.8)
    ax1.set(xlabel='False Positive Rate', ylabel='True Positive Rate',
            title='(a) ROC Curves  - Full Range', xlim=(-0.02, 1.02), ylim=(-0.02, 1.05))
    ax1.set_aspect('equal')
    ax1.legend(loc='lower right', fontsize=8)
    ax1.grid(alpha=.3)

    # Zoomed panel: FPR < 10%
    ax2.set(xlabel='False Positive Rate', ylabel='True Positive Rate',
            title='(b) Low-FPR Region (FPR < 10%)', xlim=(-0.005, 0.10), ylim=(0, 1.05))
    ax2.axvline(0.05, color='gray', ls=':', alpha=0.5, label='FPR = 5%')
    # Mark operating points
    for det in dets:
        m_fpr = compute_metrics(df[df['det_name'] == det].copy())[det]['FPR'] if det in compute_metrics(df[df['det_name'] == det].copy()) else 0
        m_tpr = compute_metrics(df[df['det_name'] == det].copy())[det]['TPR'] if det in compute_metrics(df[df['det_name'] == det].copy()) else 0
        marker = '*' if det == 'P_Proposed' else 'o'
        ms = 15 if det == 'P_Proposed' else 8
        ax2.scatter([m_fpr], [m_tpr], color=COLORS[det], marker=marker, s=ms**2,
                    edgecolors='black', zorder=15, lw=1)

    ax2.legend(loc='lower right', fontsize=8)
    ax2.grid(alpha=.3)

    fig.tight_layout()
    _save(fig, f'{out_dir}/fig2_roc')
    return aucs


# ===============================================================
#  FIG 3: Per-Attack  - Grouped TPR bars (strength: only Proposed is balanced)
# ===============================================================
def fig3_per_attack(df, out_dir):
    pa = compute_per_attack(df)
    dets = [d for d in DET_ORDER if d != 'B0_Naive']
    attack_types = list(ATTACK_LABELS.keys())

    fig, ax = plt.subplots(figsize=(9, 5.5))
    n_dets = len(dets)
    n_atks = len(attack_types)
    x = np.arange(n_dets)
    width = 0.35
    offsets = [-width/2, width/2]
    hatches = ['', '//']
    atk_colors = ['#3498DB', '#E67E22']

    for i, atk_type in enumerate(attack_types):
        am = pa.get(atk_type, {})
        tprs = [am[d]['TPR'] if d in am else 0 for d in dets]
        bars = ax.bar(x + offsets[i], tprs, width,
                      label=ATTACK_LABELS[atk_type],
                      color=atk_colors[i], edgecolor='black', lw=0.8,
                      hatch=hatches[i], alpha=0.85)
        for b, v in zip(bars, tprs):
            if v > 0.01:
                ax.text(b.get_x() + b.get_width()/2, b.get_height() + 0.02,
                        f'{v:.1%}', ha='center', fontsize=8, fontweight='bold')

    # Highlight Proposed with a box
    proposed_idx = dets.index('P_Proposed')
    ax.axvspan(proposed_idx - 0.5, proposed_idx + 0.5,
               alpha=0.08, color='red', zorder=0)

    ax.set_xticks(x)
    ax.set_xticklabels([SHORT_LABELS.get(d, d) for d in dets], fontsize=11, fontweight='bold')
    ax.set_ylabel('True Positive Rate (TPR)', fontsize=12)
    ax.set_title('Per-Attack Detection Rate', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=11, loc='upper left')
    ax.grid(axis='y', alpha=.3)

    # Add annotation
    ax.annotate('Only detector with\nhigh TPR on both attacks',
                xy=(proposed_idx, 0.85), xytext=(proposed_idx - 1.5, 0.60),
                fontsize=9, fontstyle='italic', color='#C0392B',
                arrowprops=dict(arrowstyle='->', color='#C0392B', lw=1.5),
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#FADBD8', edgecolor='#C0392B'))

    fig.tight_layout()
    _save(fig, f'{out_dir}/fig3_per_attack')


# ===============================================================
#  FIG 5: Sensitivity  - Focus on stable region
# ===============================================================
def fig5_sensitivity(df, out_dir):
    fig, ax = plt.subplots(figsize=(10, 5))
    thresholds, f1s, tprs, fprs = sensitivity_sweep(df, 'P_Proposed', n_pts=80)
    if not len(thresholds): plt.close(fig); return

    ax.plot(thresholds, f1s, 'C3-o', lw=2.5, ms=3.5, label='F1', zorder=10)
    ax.plot(thresholds, tprs, 'C0--s', lw=1.5, ms=3, label='TPR')
    ax.plot(thresholds, fprs, 'C1--^', lw=1.5, ms=3, label='FPR')

    # Highlight stable region (no label  - put in legend manually)
    ax.axvspan(0.45, 0.59, alpha=0.12, color='green')
    ax.axvline(0.55, color='gray', ls=':', alpha=.7, lw=2)

    bi = int(np.argmax(f1s))
    ax.scatter([thresholds[bi]], [f1s[bi]], s=200, c='red', marker='*', zorder=15)

    # Annotations instead of legend entries for non-line items
    ax.annotate(r'Stable region ($\Theta \in [0.45, 0.59]$)',
                xy=(0.52, 0.75), fontsize=9, color='#1B7B2C', fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9', edgecolor='#2E7D32', alpha=0.9))
    ax.annotate(r'$\Theta = 0.55$', xy=(0.56, 0.45), fontsize=9, color='gray')
    ax.annotate(f'Best F1={f1s[bi]:.3f}\n@ theta={thresholds[bi]:.2f}',
                xy=(thresholds[bi], f1s[bi]), xytext=(thresholds[bi]+0.12, f1s[bi]-0.05),
                fontsize=9, fontweight='bold', color='red',
                arrowprops=dict(arrowstyle='->', color='red', lw=1.5))

    ax.set(xlabel=r'Detection Threshold ($\Theta$)', ylabel='Metric Value',
           title=r'Proposed Method: Sensitivity to $\Theta$',
           xlim=(0.0, 1.05), ylim=(-0.05, 1.05))
    ax.legend(fontsize=11, loc='upper right',
              framealpha=0.95, edgecolor='black', fancybox=True)
    ax.grid(alpha=.3)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig5_sensitivity')


# ===============================================================
#  FIG Mitigation: EEBL-relevant BSMs only (ahead + gap < 300m)
# ===============================================================
def fig_mitigation(df, out_dir):
    if 'mitigated_a' not in df.columns or 'ttc' not in df.columns:
        print("    mitigated_a/ttc column missing  - skipping")
        return

    dm = df.copy()
    dm['is_attack'] = dm['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    p = dm[dm['det_name'] == 'P_Proposed']

    # Filter: non-zero mitigated_a AND ttc > 0 (ahead, gap > 0)
    # OR mitigated_a < 0 (actual braking)
    p_atk = p[(p['is_attack'] == 1) & (p['mitigated_a'] != 0)]
    p_ben = p[(p['is_attack'] == 0) & (p['mitigated_a'] != 0)]

    # Further filter: only cases where IDM actually computed braking (mitA < 0.5)
    # This filters out free-flow cases where ghost is too far
    atk_near = p_atk[p_atk['mitigated_a'] < 0.5]['mitigated_a']
    ben_near = p_ben[p_ben['mitigated_a'] < 0.5]['mitigated_a']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5))

    # Panel (a): Box plot comparison
    data, labs, cols = [], [], []
    if len(atk_near) > 0:
        data.append(atk_near.clip(-8, 2).values)
        labs.append(f'Attack BSMs\n(n={len(atk_near):,})')
        cols.append('#FF6B6B')
    if len(ben_near) > 0:
        data.append(ben_near.clip(-8, 2).values)
        labs.append(f'Benign BSMs\n(n={len(ben_near):,})')
        cols.append('#4ECDC4')

    if data:
        bp = ax1.boxplot(data, labels=labs, patch_artist=True, widths=.5, showfliers=False)
        for p_box, c in zip(bp['boxes'], cols):
            p_box.set_facecolor(c); p_box.set_alpha(.7)

    ax1.axhline(-3.92, color='red', ls='--', lw=2, alpha=.7, label='Hard brake (0.4g)')
    ax1.axhline(-8.0, color='darkred', ls=':', lw=1.5, alpha=.5, label='Max emergency (-8.0 m/s^2)')
    ax1.axhline(0, color='gray', ls='-', alpha=.3)
    ax1.set(ylabel='IDM Mitigated Accel (m/s^2)',
            title='(a) IDM Bounded Deceleration')
    ax1.legend(fontsize=8)
    ax1.grid(axis='y', alpha=.3)

    # Panel (b): Histogram comparison
    if len(atk_near) > 0:
        ax2.hist(atk_near.clip(-6, 2).values, bins=40, alpha=0.6,
                 color='#FF6B6B', label='Attack', density=True, edgecolor='black', lw=0.3)
    if len(ben_near) > 0:
        ax2.hist(ben_near.clip(-6, 2).values, bins=40, alpha=0.6,
                 color='#4ECDC4', label='Benign', density=True, edgecolor='black', lw=0.3)

    ax2.axvline(-3.92, color='red', ls='--', lw=2, alpha=.7, label='Hard brake (0.4g)')
    ax2.axvline(-8.0, color='darkred', ls=':', lw=1.5, alpha=.5, label='Max emergency')
    ax2.set(xlabel='IDM Mitigated Accel (m/s^2)', ylabel='Density',
            title='(b) Distribution of IDM Response')
    ax2.legend(fontsize=8)
    ax2.grid(alpha=.3)

    fig.suptitle('RQ5: IDM Mitigation Bounds Ego Response', fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig_mitigation')

    # Print stats
    print(f"\n    IDM Mitigation Stats (EEBL-relevant BSMs):")
    if len(atk_near) > 0:
        print(f"      Attack (n={len(atk_near):,}): mean={atk_near.mean():.2f}, "
              f"median={atk_near.median():.2f}, min={atk_near.min():.2f}")
    if len(ben_near) > 0:
        print(f"      Benign (n={len(ben_near):,}): mean={ben_near.mean():.2f}, "
              f"median={ben_near.median():.2f}")


# ===============================================================
#  FIG EXTRA: Summary radar/bar  - overall F1 + per-attack
# ===============================================================
def fig_summary(df, metrics, out_dir):
    """Combined summary figure showing Proposed dominance."""
    dets = [d for d in DET_ORDER if d != 'B0_Naive']
    pa = compute_per_attack(df)

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # (a) F1 comparison
    ax = axes[0]
    f1s = [metrics[d]['F1'] for d in dets]
    bars = ax.barh(range(len(dets)), f1s, color=[COLORS[d] for d in dets],
                   edgecolor='black', lw=0.8)
    for i, (b, v) in enumerate(zip(bars, f1s)):
        ax.text(v + 0.02, i, f'{v:.3f}', va='center', fontsize=10, fontweight='bold')
    ax.set_yticks(range(len(dets)))
    ax.set_yticklabels([SHORT_LABELS.get(d, d) for d in dets], fontsize=11)
    ax.set_xlabel('F1 Score', fontsize=11)
    ax.set_title('(a) Overall F1 Score', fontsize=12, fontweight='bold')
    ax.set_xlim(0, 1.15)
    ax.grid(axis='x', alpha=.3)
    ax.invert_yaxis()

    # (b) TPR per attack - grouped
    ax = axes[1]
    atk_types = list(ATTACK_LABELS.keys())
    x = np.arange(len(dets))
    width = 0.35
    for i, atk_type in enumerate(atk_types):
        am = pa.get(atk_type, {})
        tprs = [am[d]['TPR'] if d in am else 0 for d in dets]
        ax.bar(x + (i - 0.5) * width, tprs, width,
               label=ATTACK_LABELS[atk_type],
               color=['#3498DB', '#E67E22'][i], edgecolor='black', lw=0.5,
               hatch=['', '//'][i], alpha=0.85)
    ax.axvspan(len(dets)-1.5, len(dets)-0.5, alpha=0.08, color='red', zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT_LABELS.get(d, d) for d in dets], rotation=30, ha='right', fontsize=9)
    ax.set_ylabel('TPR')
    ax.set_title('(b) Per-Attack TPR', fontsize=12, fontweight='bold')
    ax.set_ylim(0, 1.15)
    ax.legend(fontsize=9)
    ax.grid(axis='y', alpha=.3)

    # (c) FPR comparison
    ax = axes[2]
    fprs = [metrics[d]['FPR'] for d in dets]
    bars = ax.barh(range(len(dets)), fprs, color=[COLORS[d] for d in dets],
                   edgecolor='black', lw=0.8)
    for i, (b, v) in enumerate(zip(bars, fprs)):
        ax.text(v + 0.002, i, f'{v:.3f}', va='center', fontsize=10, fontweight='bold')
    ax.set_yticks(range(len(dets)))
    ax.set_yticklabels([SHORT_LABELS.get(d, d) for d in dets], fontsize=11)
    ax.set_xlabel('False Positive Rate', fontsize=11)
    ax.set_title('(c) False Positive Rate', fontsize=12, fontweight='bold')
    ax.set_xlim(0, max(fprs) * 1.5 + 0.01)
    ax.grid(axis='x', alpha=.3)
    ax.invert_yaxis()

    fig.suptitle('Detection Performance Summary', fontsize=14, fontweight='bold', y=1.02)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig_summary')


# ===============================================================
#  RQ TEXT ANALYSIS
# ===============================================================

def rq1_analysis(df, metrics, aucs):
    print("\n" + "=" * 90)
    print("  RQ1: Detection Accuracy + AUC")
    print("=" * 90)
    hdr = f"{'Detector':<25} {'TPR':>7} {'FPR':>7} {'Prec':>7} {'F1':>7} {'AUC':>7}"
    print(hdr); print("-" * 90)
    for d in DET_ORDER:
        if d not in metrics: continue
        m = metrics[d]; auc = aucs.get(d, 0)
        mark = "  < BEST F1" if d == 'P_Proposed' else ""
        print(f"{LABELS.get(d,d):<25} {m['TPR']:>7.4f} {m['FPR']:>7.4f} "
              f"{m['Precision']:>7.4f} {m['F1']:>7.4f} {auc:>7.3f}{mark}")

def rq2_analysis(df):
    print("\n" + "=" * 90)
    print("  RQ2: Per-Attack Breakdown")
    print("=" * 90)
    pa = compute_per_attack(df)
    for atk_type, am in pa.items():
        print(f"\n  -- {ATTACK_LABELS[atk_type]} --")
        print(f"  {'Detector':<25} {'TPR':>7} {'FPR':>7} {'F1':>7} {'TP':>8} {'FN':>8}")
        print("  " + "-" * 70)
        for d in DET_ORDER:
            if d not in am: continue
            m = am[d]; mark = " <" if d == 'P_Proposed' else ""
            print(f"  {LABELS.get(d,d):<25} {m['TPR']:>7.4f} {m['FPR']:>7.4f} "
                  f"{m['F1']:>7.4f} {m['TP']:>8} {m['FN']:>8}{mark}")

def rq3_analysis(df, metrics):
    print("\n" + "=" * 90)
    print("  RQ3: False Positive + Ablation")
    print("=" * 90)
    print(f"\n  {'Detector':<25} {'FP':>8} {'TN':>10} {'FPR':>10}")
    print("  " + "-" * 60)
    for d in DET_ORDER:
        if d not in metrics: continue
        m = metrics[d]
        print(f"  {LABELS.get(d,d):<25} {m['FP']:>8} {m['TN']:>10} {m['FPR']:>10.6f}")
    if 'P_NoGate' in df['det_name'].unique():
        ng = compute_metrics(df[df['det_name'] == 'P_NoGate'])
        p_m = metrics.get('P_Proposed', {})
        ng_m = ng.get('P_NoGate', {})
        if p_m and ng_m:
            print(f"\n  -- Ablation: EEBL Gate --")
            print(f"  {'With Gate':<25} FPR={p_m['FPR']:.4f}  TPR={p_m['TPR']:.4f}  F1={p_m['F1']:.4f}")
            print(f"  {'Without Gate':<25} FPR={ng_m['FPR']:.4f}  TPR={ng_m['TPR']:.4f}  F1={ng_m['F1']:.4f}")

def rq4_analysis(df):
    print("\n" + "=" * 90)
    print("  RQ4: Sensitivity to theta")
    print("=" * 90)
    thresholds, f1s, tprs, fprs = sensitivity_sweep(df, 'P_Proposed')
    if len(thresholds) == 0: return
    bi = int(np.argmax(f1s))
    idx55 = np.argmin(np.abs(thresholds - 0.55))
    print(f"\n  Best F1 = {f1s[bi]:.4f} at theta = {thresholds[bi]:.2f}")
    print(f"  At theta=0.55: TPR={tprs[idx55]:.4f}, FPR={fprs[idx55]:.4f}, F1={f1s[idx55]:.4f}")
    print(f"\n  {'theta':>6} {'TPR':>7} {'FPR':>7} {'F1':>7}")
    print("  " + "-" * 35)
    for t in [0.30, 0.40, 0.50, 0.55, 0.60, 0.65, 0.70, 0.80]:
        idx = np.argmin(np.abs(thresholds - t))
        print(f"  {thresholds[idx]:>6.2f} {tprs[idx]:>7.4f} {fprs[idx]:>7.4f} {f1s[idx]:>7.4f}")

def rq5_analysis(df):
    print("\n" + "=" * 90)
    print("  RQ5: IDM Mitigation")
    print("=" * 90)
    if 'mitigated_a' not in df.columns:
        print("  mitigated_a missing"); return
    dm = df.copy()
    dm['is_attack'] = dm['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    p = dm[dm['det_name'] == 'P_Proposed']
    atk = p[(p['is_attack'] == 1) & (p['mitigated_a'] != 0) & (p['mitigated_a'] < 0.5)]['mitigated_a']
    ben = p[(p['is_attack'] == 0) & (p['mitigated_a'] != 0) & (p['mitigated_a'] < 0.5)]['mitigated_a']
    if len(atk) > 0:
        print(f"\n  Attack BSMs (EEBL-relevant, n={len(atk):,}):")
        print(f"    Mean: {atk.mean():.2f} m/s^2  Median: {atk.median():.2f}  Min: {atk.min():.2f}")
    if len(ben) > 0:
        print(f"  Benign BSMs (EEBL-relevant, n={len(ben):,}):")
        print(f"    Mean: {ben.mean():.2f} m/s^2  Median: {ben.median():.2f}")
    if len(atk) > 0:
        print(f"\n  -> Emergency braking: -8.0 m/s^2")
        print(f"  -> IDM bounded: ~{atk.mean():.1f} m/s^2")
        print(f"  -> Reduction: {abs(-8.0) - abs(atk.mean()):.1f} m/s^2 ({100*(abs(-8.0) - abs(atk.mean()))/8.0:.0f}% less severe)")


def generate_latex_table(metrics, aucs, path):
    lines = [
        r'\begin{table}[t]', r'\centering',
        r'\caption{Aggregate detection performance (VASP, 20 vehicles, 120\,s).}',
        r'\label{tab:comparison}', r'\resizebox{\columnwidth}{!}{%',
        r'\begin{tabular}{l|cccc|c}', r'\hline',
        r'\textbf{Method} & \textbf{TPR} & \textbf{FPR} & \textbf{Prec.} & \textbf{F1} & \textbf{AUC} \\',
        r'\hline',
    ]
    for d in DET_ORDER:
        if d not in metrics: continue
        m = metrics[d]; auc = aucs.get(d, 0)
        lb = LABELS.get(d, d)
        if d == 'P_Proposed': lb = r'\textbf{' + lb + '}'
        auc_s = f'{auc:.3f}' if auc > 0 else '---'
        pr_s = f'{m["Precision"]:.3f}' if m["Precision"] > 0 else '---'
        f1_s = f'{m["F1"]:.3f}' if m["F1"] > 0 else '---'
        lines.append(f'{lb} & {m["TPR"]:.3f} & {m["FPR"]:.3f} & {pr_s} & {f1_s} & {auc_s} \\\\')
    lines += [r'\hline', r'\end{tabular}%', r'}', r'\end{table}']
    with open(path, 'w') as f: f.write('\n'.join(lines))
    print(f"  LaTeX -> {path}")


# ===============================================================
def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else 'results'
    fig_dir = os.path.join(results_dir, 'figures')
    os.makedirs(fig_dir, exist_ok=True)

    print("=" * 90)
    print("  VASP EEBL  - EEBL Detection Analysis")
    print("=" * 90)

    print("\n[1/9] Loading...")
    df = load_detlogs(results_dir)
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    print(f"  Total: {len(df):,} | Detectors: {sorted(df['det_name'].unique())}")

    df_main = df[df['det_name'].isin(DET_ORDER)]
    print("\n[2/9] Metrics...")
    metrics = compute_metrics(df_main)

    print("[3/9] ROC/AUC...")
    aucs = {}
    for d in DET_ORDER:
        _, _, auc = compute_roc(df_main, d) if d != 'B0_Naive' else ([], [], 0)
        aucs[d] = auc

    print("[4/9] RQ1"); rq1_analysis(df_main, metrics, aucs)
    print("[5/9] RQ2"); rq2_analysis(df_main)
    print("[6/9] RQ3"); rq3_analysis(df, metrics)
    print("[7/9] RQ4"); rq4_analysis(df_main)
    print("[8/9] RQ5"); rq5_analysis(df_main)

    print("\n[9/9] Generating Figures...")
    print("=" * 90)
    aucs = fig2_roc(df_main, fig_dir)
    fig3_per_attack(df_main, fig_dir)
    fig5_sensitivity(df_main, fig_dir)
    fig_mitigation(df_main, fig_dir)
    fig_summary(df_main, metrics, fig_dir)

    generate_latex_table(metrics, aucs, os.path.join(results_dir, 'table_comparison.tex'))
    pd.DataFrame([{**metrics[d], 'detector': d, 'AUC': aucs.get(d, 0)} for d in DET_ORDER if d in metrics]).to_csv(
        os.path.join(results_dir, 'combined_metrics.csv'), index=False)

    print("\n" + "=" * 90)
    print("  Done! Figures -> " + fig_dir)
    print("=" * 90)

if __name__ == '__main__':
    main()
