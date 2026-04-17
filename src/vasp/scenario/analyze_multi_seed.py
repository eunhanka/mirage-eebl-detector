#!/usr/bin/env python3
"""
===============================================================
  analyze_multi_seed.py -- Multi-Seed Analysis + All Paper Figures
  
  Reads: results/seed{0..N}/detlog-*.csv
  Generates all figures from the paper with error bars/bands:
    fig2_roc.png         -- ROC curves (mean +/- std band)
    fig3_per_attack.png  -- Per-attack TPR bars (with error bars)
    fig5_sensitivity.png -- Threshold sensitivity (with bands)
    fig_mitigation.png   -- IDM mitigation distributions
  Plus text analysis: main table, latency, ablation
  
  Usage: python3 analyze_multi_seed.py [results_dir]
===============================================================
"""

import os, sys, glob, warnings
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore')

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# -- Global font settings: minimum 14pt for paper readability --
plt.rcParams.update({
    'font.size': 14,
    'axes.titlesize': 18,
    'axes.labelsize': 16,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 14,
    'figure.titlesize': 18,
})

# -- Config (same as original analyze_vasp_v3.py) --
DET_ORDER = ['B0_Naive', 'B1_Threshold', 'B2_VCADS', 'B3_F2MD', 'P_Proposed']
LABELS = {
    'B0_Naive': 'B0: No Detection', 'B1_Threshold': 'B1: Threshold',
    'B2_VCADS': 'B2: VCADS', 'B3_F2MD': 'B3: F2MD/VASP',
    'P_Proposed': 'Proposed (Ours)', 'P_NoGate': 'Proposed (No Gate)',
}
SHORT_LABELS = {
    'B1_Threshold': 'Threshold', 'B2_VCADS': 'VCADS',
    'B3_F2MD': 'F2MD', 'P_Proposed': 'Proposed',
}
COLORS = {
    'B0_Naive': '#AAAAAA', 'B1_Threshold': '#5DADE2',
    'B2_VCADS': '#F39C12', 'B3_F2MD': '#2ECC71',
    'P_Proposed': '#E74C3C', 'P_NoGate': '#9B59B6',
}
ATTACK_MAP = {
    'Genuine': 0, 'FakeEEBLJustAttack': 1,
    'FakeEEBLStopPositionUpdateAfterAttack': 1,
}
ATTACK_LABELS = {
    'FakeEEBLJustAttack': r'$\mathcal{A}_1$ (NoStop)',
    'FakeEEBLStopPositionUpdateAfterAttack': r'$\mathcal{A}_2$ (WithStop)',
}
CHECK_WEIGHTS = {
    'TTC_HIGH': 0.15, 'TTC_RECEDING': 0.35, 'NEW_SENDER': 0.20,
    'PHYS_LIMIT': 0.20, 'CROSS_FIELD': 0.15, 'BRAKE_MISMATCH': 0.15,
    'TRAJ_INCONS': 0.20, 'POST_EEBL_NO_STOP': 0.30,
    'POS_SPD_MISMATCH': 0.15, 'FROZEN_POS': 0.60,
}
CHECK_NAMES_SHORT = {
    'TTC_HIGH': '1a', 'TTC_RECEDING': "1a'", 'NEW_SENDER': '1b',
    'PHYS_LIMIT': '2a', 'CROSS_FIELD': '2b', 'BRAKE_MISMATCH': '2c',
    'TRAJ_INCONS': '3a', 'POST_EEBL_NO_STOP': '3b',
    'POS_SPD_MISMATCH': '3c', 'FROZEN_POS': '4',
}
THETA = 0.55


# =======================================================
#  LOADING
# =======================================================

def load_all(results_dir):
    seed_dirs = sorted(glob.glob(os.path.join(results_dir, 'seed*')))
    if seed_dirs:
        frames = []
        for sd in seed_dirs:
            seed = int(os.path.basename(sd).replace('seed', ''))
            for f in glob.glob(os.path.join(sd, 'detlog-*.csv')):
                try:
                    df = pd.read_csv(f)
                    if len(df) > 0:
                        df['seed'] = seed
                        frames.append(df)
                except: pass
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return df, len(seed_dirs)
    else:
        # Flat directory fallback
        frames = []
        for f in glob.glob(os.path.join(results_dir, 'detlog-*.csv')):
            try:
                df = pd.read_csv(f)
                if len(df) > 0:
                    df['seed'] = 0
                    frames.append(df)
            except: pass
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return df, 1


# =======================================================
#  METRICS
# =======================================================

def calc_metrics(sub):
    y, p = sub['is_attack'].values, sub['suspicious'].values
    tp=((y==1)&(p==1)).sum(); fp=((y==0)&(p==1)).sum()
    tn=((y==0)&(p==0)).sum(); fn=((y==1)&(p==0)).sum()
    tpr=tp/max(tp+fn,1); fpr=fp/max(fp+tn,1)
    prec=tp/max(tp+fp,1); f1=2*prec*tpr/max(prec+tpr,1e-9)
    return {'TPR':tpr,'FPR':fpr,'Precision':prec,'F1':f1,'TP':tp,'FP':fp,'TN':tn,'FN':fn}

def metrics_per_seed(df, det, atk_type=None):
    sub = df[df['det_name']==det]
    if atk_type: sub = sub[sub['attack_type'].isin([atk_type, 'Genuine'])]
    return [calc_metrics(sub[sub['seed']==s]) for s in sorted(sub['seed'].unique()) if len(sub[sub['seed']==s])>0]

def ms(vals):
    if not vals: return 0, 0
    return np.mean(vals), np.std(vals)

def ms_str(vals):
    m, s = ms(vals)
    return f"{m:.3f}+/-{s:.3f}" if s > 0 else f"{m:.3f}"

def _save(fig, base):
    fig.savefig(f'{base}.png', dpi=300, bbox_inches='tight')
    fig.savefig(f'{base}.pdf', bbox_inches='tight')
    plt.close(fig)
    print(f"    -> {base}.png/.pdf")


# =======================================================
#  FIG 2: ROC Curves (with confidence band)
# =======================================================

def fig2_roc(df, out_dir, n_seeds):
    print("  [Fig 2] ROC curves...")
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))
    dets = [d for d in DET_ORDER if d != 'B0_Naive']
    aucs = {}
    n_pts = 200

    for det in dets:
        lw = 3 if det == 'P_Proposed' else 1.5
        ls = '-' if det == 'P_Proposed' else '--'
        zorder = 10 if det == 'P_Proposed' else 5

        if n_seeds > 1:
            # Compute ROC per seed, then mean +/- std
            all_tprs = []
            seed_aucs = []
            fpr_grid = np.linspace(0, 1, n_pts)
            for seed in sorted(df['seed'].unique()):
                sub = df[(df['det_name']==det) & (df['seed']==seed)]
                if sub.empty: continue
                y = sub['is_attack'].values; s = sub['score'].values
                fprs_s, tprs_s = [], []
                for t in np.linspace(0, 1, n_pts):
                    pred=(s>=t).astype(int)
                    tp=((y==1)&(pred==1)).sum(); fp=((y==0)&(pred==1)).sum()
                    fn=((y==1)&(pred==0)).sum(); tn=((y==0)&(pred==0)).sum()
                    tprs_s.append(tp/max(tp+fn,1)); fprs_s.append(fp/max(fp+tn,1))
                # Sort FPR-TPR pairs together by FPR
                paired = sorted(zip(fprs_s, tprs_s), key=lambda x: x[0])
                fprs_sorted = [p[0] for p in paired]
                tprs_sorted = [p[1] for p in paired]
                # Interpolate to common FPR grid
                tprs_interp = np.interp(fpr_grid, fprs_sorted, tprs_sorted)
                all_tprs.append(tprs_interp)
                # AUC via trapezoidal on correctly paired data
                auc_s = np.trapz(tprs_sorted, fprs_sorted)
                seed_aucs.append(auc_s)
            
            if all_tprs:
                mean_tpr = np.mean(all_tprs, axis=0)
                std_tpr = np.std(all_tprs, axis=0)
                auc_mean = np.mean(seed_aucs)
                aucs[det] = auc_mean
                label = f'{LABELS[det]} (AUC={auc_mean:.3f})'
                for ax in [ax1, ax2]:
                    ax.plot(fpr_grid, mean_tpr, color=COLORS[det], lw=lw, ls=ls, label=label, zorder=zorder)
                    ax.fill_between(fpr_grid, mean_tpr-std_tpr, np.clip(mean_tpr+std_tpr,0,1),
                                    color=COLORS[det], alpha=0.12, zorder=zorder-1)
        else:
            # Single seed: same as original
            sub = df[df['det_name']==det]
            if sub.empty: continue
            y=sub['is_attack'].values; s=sub['score'].values
            fprs_s, tprs_s = [], []
            for t in np.linspace(0,1,n_pts):
                pred=(s>=t).astype(int)
                tp=((y==1)&(pred==1)).sum(); fp=((y==0)&(pred==1)).sum()
                fn=((y==1)&(pred==0)).sum(); tn=((y==0)&(pred==0)).sum()
                tprs_s.append(tp/max(tp+fn,1)); fprs_s.append(fp/max(fp+tn,1))
            auc = sum(abs(fprs_s[i]-fprs_s[i-1])*(tprs_s[i]+tprs_s[i-1])/2 for i in range(1,len(fprs_s)))
            aucs[det] = auc
            label = f'{LABELS[det]} (AUC={auc:.3f})'
            for ax in [ax1, ax2]:
                ax.plot(fprs_s, tprs_s, color=COLORS[det], lw=lw, ls=ls, label=label, zorder=zorder)

    ax1.plot([0,1],[0,1],'k--',alpha=.3,lw=0.8)
    ax1.set(xlabel='False Positive Rate', ylabel='True Positive Rate',
            title='(a) ROC Curves -- Full Range', xlim=(-0.02,1.02), ylim=(-0.02,1.05))
    ax1.set_aspect('equal'); ax1.legend(loc='lower right', fontsize=14); ax1.grid(alpha=.3)
    ax2.set(xlabel='False Positive Rate', ylabel='True Positive Rate',
            title='(b) Low-FPR Region (FPR < 10%)', xlim=(-0.005,0.10), ylim=(0,1.05))
    ax2.axvline(0.05, color='gray', ls=':', alpha=0.5)
    ax2.legend(loc='lower right', fontsize=14); ax2.grid(alpha=.3)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig2_roc')
    return aucs


# =======================================================
#  FIG 3: Per-Attack TPR (with error bars)
# =======================================================

def fig3_per_attack(df, out_dir, n_seeds):
    print("  [Fig 3] Per-attack TPR...")
    dets = [d for d in DET_ORDER if d != 'B0_Naive']
    attack_types = list(ATTACK_LABELS.keys())
    
    fig, ax = plt.subplots(figsize=(11, 7))
    x = np.arange(len(dets))
    width = 0.35
    offsets = [-width/2, width/2]
    hatches = ['', '//']
    atk_colors = ['#3498DB', '#E67E22']

    for i, atk_type in enumerate(attack_types):
        means, stds = [], []
        for det in dets:
            ps = metrics_per_seed(df, det, atk_type)
            tprs = [m['TPR'] for m in ps] if ps else [0]
            means.append(np.mean(tprs)); stds.append(np.std(tprs))
        
        bars = ax.bar(x + offsets[i], means, width, yerr=stds if n_seeds > 1 else None,
                      capsize=4, label=ATTACK_LABELS[atk_type],
                      color=atk_colors[i], edgecolor='black', lw=0.8,
                      hatch=hatches[i], alpha=0.85, error_kw={'lw':1.5})
        for b, m, s in zip(bars, means, stds):
            label_text = f'{m:.1%}' if n_seeds <= 1 else f'{m:.1%}\n+/-{s:.1%}'
            if m > 0.01:
                ax.text(b.get_x()+b.get_width()/2, b.get_height()+0.03,
                        label_text, ha='center', fontsize=14, fontweight='bold')

    proposed_idx = dets.index('P_Proposed')
    ax.axvspan(proposed_idx-0.5, proposed_idx+0.5, alpha=0.08, color='red', zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels([SHORT_LABELS.get(d,d) for d in dets], fontsize=16, fontweight='bold')
    ax.set_ylabel('True Positive Rate (TPR)', fontsize=16)
    seeds_note = f' (mean +/- std, {n_seeds} seeds)' if n_seeds > 1 else ''
    ax.set_title(f'Per-Attack Detection Rate{seeds_note}', fontsize=18, fontweight='bold')
    ax.set_ylim(0, 1.25)
    ax.legend(fontsize=15, loc='upper left')
    ax.grid(axis='y', alpha=.3)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig3_per_attack')


# =======================================================
#  FIG 5: Sensitivity to theta (with bands)
# =======================================================

def fig5_sensitivity(df, out_dir, n_seeds):
    print("  [Fig 5] Sensitivity to theta...")
    n_pts = 80
    thresholds = np.linspace(0.05, 1.0, n_pts)
    
    if n_seeds > 1:
        all_f1, all_tpr, all_fpr = [], [], []
        for seed in sorted(df['seed'].unique()):
            sub = df[(df['det_name']=='P_Proposed') & (df['seed']==seed)]
            if sub.empty: continue
            y=sub['is_attack'].values; s=sub['score'].values
            f1s, tprs, fprs = [], [], []
            for t in thresholds:
                pred=(s>=t).astype(int)
                tp=((y==1)&(pred==1)).sum(); fp=((y==0)&(pred==1)).sum()
                fn=((y==1)&(pred==0)).sum(); tn=((y==0)&(pred==0)).sum()
                pr=tp/max(tp+fp,1); re=tp/max(tp+fn,1)
                f1s.append(2*pr*re/max(pr+re,1e-9)); tprs.append(re); fprs.append(fp/max(fp+tn,1))
            all_f1.append(f1s); all_tpr.append(tprs); all_fpr.append(fprs)
        
        mean_f1=np.mean(all_f1,axis=0); std_f1=np.std(all_f1,axis=0)
        mean_tpr=np.mean(all_tpr,axis=0); std_tpr=np.std(all_tpr,axis=0)
        mean_fpr=np.mean(all_fpr,axis=0); std_fpr=np.std(all_fpr,axis=0)
    else:
        sub=df[df['det_name']=='P_Proposed']
        if sub.empty: return
        y=sub['is_attack'].values; s=sub['score'].values
        mean_f1, mean_tpr, mean_fpr = [], [], []
        for t in thresholds:
            pred=(s>=t).astype(int)
            tp=((y==1)&(pred==1)).sum(); fp=((y==0)&(pred==1)).sum()
            fn=((y==1)&(pred==0)).sum(); tn=((y==0)&(pred==0)).sum()
            pr=tp/max(tp+fp,1); re=tp/max(tp+fn,1)
            mean_f1.append(2*pr*re/max(pr+re,1e-9)); mean_tpr.append(re); mean_fpr.append(fp/max(fp+tn,1))
        mean_f1=np.array(mean_f1); mean_tpr=np.array(mean_tpr); mean_fpr=np.array(mean_fpr)
        std_f1=std_tpr=std_fpr=np.zeros_like(mean_f1)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(thresholds, mean_f1, 'C3-o', lw=2.5, ms=3.5, label='F1', zorder=10)
    ax.plot(thresholds, mean_tpr, 'C0--s', lw=1.5, ms=3, label='TPR')
    ax.plot(thresholds, mean_fpr, 'C1--^', lw=1.5, ms=3, label='FPR')
    if n_seeds > 1:
        ax.fill_between(thresholds, mean_f1-std_f1, np.clip(mean_f1+std_f1,0,1), color='C3', alpha=0.12)
        ax.fill_between(thresholds, mean_tpr-std_tpr, np.clip(mean_tpr+std_tpr,0,1), color='C0', alpha=0.08)

    ax.axvspan(0.45, 0.59, alpha=0.12, color='green')
    ax.axvline(0.55, color='gray', ls=':', alpha=.7, lw=2)
    bi = int(np.argmax(mean_f1))
    ax.scatter([thresholds[bi]], [mean_f1[bi]], s=200, c='red', marker='*', zorder=15)
    ax.annotate(r'Stable region ($\Theta \in [0.45, 0.59]$)',
                xy=(0.52, 0.75), fontsize=14, color='#1B7B2C', fontstyle='italic',
                bbox=dict(boxstyle='round,pad=0.3', facecolor='#E8F5E9', edgecolor='#2E7D32', alpha=0.9))
    seeds_note = f' ({n_seeds} seeds, mean +/- std)' if n_seeds > 1 else ''
    ax.set(xlabel=r'Detection Threshold ($\Theta$)', ylabel='Metric Value',
           title=f'Proposed Method: Sensitivity to $\\Theta${seeds_note}',
           xlim=(0.0, 1.05), ylim=(-0.05, 1.05))
    ax.legend(fontsize=14, loc='upper right')
    ax.grid(alpha=.3)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig5_sensitivity')


# =======================================================
#  FIG Ablation Heatmap (RQ5)
# =======================================================

def fig_ablation(df, out_dir):
    print("  [Fig A] Ablation heatmap...")
    proposed = df[df['det_name']=='P_Proposed'].copy()
    if proposed.empty: return
    
    checks = list(CHECK_NAMES_SHORT.keys())
    labels = [CHECK_NAMES_SHORT[c] for c in checks]
    scopes = ['Overall', r'$\mathcal{A}_1$', r'$\mathcal{A}_2$']
    atk_types = [None, 'FakeEEBLJustAttack', 'FakeEEBLStopPositionUpdateAfterAttack']
    
    # Build DeltaF1 matrix: rows=checks, cols=[Overall, A1, A2]
    delta_f1 = np.zeros((len(checks), 3))
    delta_tpr = np.zeros((len(checks), 3))
    
    for j, at in enumerate(atk_types):
        sub = proposed if at is None else proposed[proposed['attack_type'].isin([at, 'Genuine'])]
        base = _ablation_metrics(sub)
        for i, ck in enumerate(checks):
            m = _ablation_metrics(sub, excl=ck)
            delta_f1[i, j] = m['F1'] - base['F1']
            delta_tpr[i, j] = m['TPR'] - base['TPR']
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 7))
    
    # Panel (a): DeltaF1 heatmap
    vmax = max(abs(delta_f1.min()), abs(delta_f1.max()), 0.01)
    im1 = ax1.imshow(delta_f1, cmap='RdYlGn_r', aspect='auto', vmin=-vmax, vmax=vmax)
    ax1.set_xticks(range(3)); ax1.set_xticklabels(scopes, fontsize=16)
    ax1.set_yticks(range(len(labels))); ax1.set_yticklabels([f'-Check {l}' for l in labels], fontsize=14)
    for i in range(len(checks)):
        for j in range(3):
            v = delta_f1[i,j]
            color = 'white' if abs(v) > vmax*0.6 else 'black'
            ax1.text(j, i, f'{v:+.3f}', ha='center', va='center', fontsize=14, fontweight='bold', color=color)
    ax1.set_title(r'(a) $\Delta$F1 When Removing Each Check', fontsize=18, fontweight='bold')
    cb1 = plt.colorbar(im1, ax=ax1, shrink=0.8)
    cb1.set_label(r'$\Delta$F1', fontsize=14)
    cb1.ax.tick_params(labelsize=14)
    
    # Panel (b): DeltaTPR heatmap
    vmax2 = max(abs(delta_tpr.min()), abs(delta_tpr.max()), 0.01)
    im2 = ax2.imshow(delta_tpr, cmap='RdYlGn_r', aspect='auto', vmin=-vmax2, vmax=vmax2)
    ax2.set_xticks(range(3)); ax2.set_xticklabels(scopes, fontsize=16)
    ax2.set_yticks(range(len(labels))); ax2.set_yticklabels([f'-Check {l}' for l in labels], fontsize=14)
    for i in range(len(checks)):
        for j in range(3):
            v = delta_tpr[i,j]
            color = 'white' if abs(v) > vmax2*0.6 else 'black'
            ax2.text(j, i, f'{v:+.3f}', ha='center', va='center', fontsize=14, fontweight='bold', color=color)
    ax2.set_title(r'(b) $\Delta$TPR When Removing Each Check', fontsize=18, fontweight='bold')
    cb2 = plt.colorbar(im2, ax=ax2, shrink=0.8)
    cb2.set_label(r'$\Delta$TPR', fontsize=14)
    cb2.ax.tick_params(labelsize=14)
    
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig_ablation')


# =======================================================
#  FIG Mitigation (same as original)
# =======================================================

def fig_mitigation(df, out_dir):
    print("  [Fig M] IDM Mitigation...")
    if 'mitigated_a' not in df.columns:
        print("    mitigated_a column missing -- skipping"); return
    p = df[df['det_name']=='P_Proposed']
    atk = p[(p['is_attack']==1) & (p['mitigated_a']!=0) & (p['mitigated_a']<0.5)]['mitigated_a']
    ben = p[(p['is_attack']==0) & (p['mitigated_a']!=0) & (p['mitigated_a']<0.5)]['mitigated_a']

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    data, labs, cols = [], [], []
    if len(atk)>0: data.append(atk.clip(-8,2).values); labs.append(f'Attack\n(n={len(atk):,})'); cols.append('#FF6B6B')
    if len(ben)>0: data.append(ben.clip(-8,2).values); labs.append(f'Benign\n(n={len(ben):,})'); cols.append('#4ECDC4')
    if data:
        bp = ax1.boxplot(data, labels=labs, patch_artist=True, widths=.5, showfliers=False)
        for box, c in zip(bp['boxes'], cols): box.set_facecolor(c); box.set_alpha(.7)
    ax1.axhline(-3.92, color='red', ls='--', lw=2, alpha=.7, label='Hard brake (0.4g)')
    ax1.axhline(-8.0, color='darkred', ls=':', lw=1.5, alpha=.5, label='Max emergency')
    ax1.set(ylabel='IDM Mitigated Accel (m/s^2)', title='(a) IDM Bounded Deceleration')
    ax1.legend(fontsize=14); ax1.grid(axis='y', alpha=.3)
    if len(atk)>0:
        ax2.hist(atk.clip(-6,2).values, bins=40, alpha=0.6, color='#FF6B6B', label='Attack', density=True, edgecolor='black', lw=0.3)
    if len(ben)>0:
        ax2.hist(ben.clip(-6,2).values, bins=40, alpha=0.6, color='#4ECDC4', label='Benign', density=True, edgecolor='black', lw=0.3)
    ax2.axvline(-3.92, color='red', ls='--', lw=2, alpha=.7)
    ax2.set(xlabel='IDM Mitigated Accel (m/s^2)', ylabel='Density', title='(b) Distribution')
    ax2.legend(fontsize=14); ax2.grid(alpha=.3)
    fig.tight_layout()
    _save(fig, f'{out_dir}/fig_mitigation')


# =======================================================
#  TEXT: Main Table (RQ1)
# =======================================================

def rq1_table(df, n_seeds, aucs):
    print("\n" + "=" * 95)
    print(f"  RQ1: Main Comparison Table ({n_seeds} seed{'s' if n_seeds>1 else ''})")
    print("=" * 95)
    print(f"\n  {'Detector':<22} {'TPR':>14} {'FPR':>14} {'Prec':>14} {'F1':>14}")
    print("  " + "-" * 70)
    
    for det in DET_ORDER:
        ps = metrics_per_seed(df, det)
        if not ps: continue
        tpr_s = ms_str([m['TPR'] for m in ps])
        fpr_s = ms_str([m['FPR'] for m in ps])
        pre_s = ms_str([m['Precision'] for m in ps])
        f1_s  = ms_str([m['F1'] for m in ps])
        mark = " <" if det == 'P_Proposed' else ""
        print(f"  {LABELS[det]:<22} {tpr_s:>14} {fpr_s:>14} {pre_s:>14} {f1_s:>14}{mark}")


# =======================================================
#  TEXT: Per-Attack (RQ2)
# =======================================================

def rq2_per_attack(df, n_seeds):
    print("\n" + "=" * 95)
    print(f"  RQ2: Per-Attack Breakdown ({n_seeds} seeds)")
    print("=" * 95)
    for atk_type, atk_label in ATTACK_LABELS.items():
        print(f"\n  -- {atk_label} --")
        print(f"  {'Detector':<22} {'TPR':>14} {'F1':>14}")
        print("  " + "-" * 55)
        for det in DET_ORDER:
            ps = metrics_per_seed(df, det, atk_type)
            if not ps: continue
            print(f"  {LABELS[det]:<22} {ms_str([m['TPR'] for m in ps]):>14} {ms_str([m['F1'] for m in ps]):>14}")


# =======================================================
#  TEXT: Detection Latency
# =======================================================

def analysis_latency(df):
    print("\n" + "=" * 95)
    print("  Detection Latency")
    print("=" * 95)
    atk_types = {'FakeEEBLJustAttack': 'A1', 'FakeEEBLStopPositionUpdateAfterAttack': 'A2'}
    print(f"\n  {'Detector':<18} {'Atk':>4} {'Mean(s)':>10} {'Median(s)':>10} {'BSMs missed':>14}")
    print("  " + "-" * 60)
    
    for det in ['B1_Threshold', 'B2_VCADS', 'B3_F2MD', 'P_Proposed']:
        for at, al in atk_types.items():
            sub = df[(df['det_name']==det) & (df['attack_type']==at)]
            if sub.empty: continue
            lats, bsms = [], []
            for (seed, hv), grp in sub.groupby(['seed','hv_id']):
                grp = grp.sort_values('time')
                det_rows = grp[grp['suspicious']==1]
                if len(det_rows) > 0:
                    lat = det_rows['time'].iloc[0] - grp['time'].iloc[0]
                    lats.append(lat)
                    bsms.append(len(grp[grp['time'] < det_rows['time'].iloc[0]]))
            if lats:
                print(f"  {LABELS.get(det,''):<18} {al:>4} {np.mean(lats):>6.2f}+/-{np.std(lats):.2f} {np.median(lats):>6.2f}s {np.mean(bsms):>8.1f}+/-{np.std(bsms):.1f}")
            else:
                print(f"  {LABELS.get(det,''):<18} {al:>4} {'no detection':>10} {'---':>10} {'---':>14}")


# =======================================================
#  TEXT: Ablation (RQ5) -- overall + per-attack
# =======================================================

def _rescore(reason, excl):
    if pd.isna(reason) or reason == 'PASS': return 0.0
    return min(sum(CHECK_WEIGHTS.get(c.strip(),0) for c in reason.split(';') if c.strip()!=excl), 1.0)

def _ablation_metrics(sub, excl=None):
    """Compute metrics for a subset, optionally excluding one check."""
    y = sub['is_attack'].values
    if excl:
        scores = sub['reason'].apply(lambda r: _rescore(r, excl)).values
    else:
        scores = sub['score'].values
    pred = (scores >= THETA).astype(int)
    tp=((y==1)&(pred==1)).sum(); fp=((y==0)&(pred==1)).sum()
    fn=((y==1)&(pred==0)).sum(); tn=((y==0)&(pred==0)).sum()
    tpr=tp/max(tp+fn,1); fpr=fp/max(fp+tn,1)
    f1=2*tp/max(2*tp+fp+fn,1)
    return {'TPR':tpr, 'FPR':fpr, 'F1':f1}

def analysis_ablation(df):
    print("\n" + "=" * 95)
    print("  RQ5: Per-Check Ablation (Proposed)")
    print("=" * 95)
    proposed = df[df['det_name']=='P_Proposed'].copy()
    if proposed.empty: print("  No data"); return
    
    # --- Overall ---
    base = _ablation_metrics(proposed)
    print(f"\n  Full Model: TPR={base['TPR']:.4f}  FPR={base['FPR']:.4f}  F1={base['F1']:.4f}")
    print(f"\n  {'Remove':>8} {'TPR':>8} {'FPR':>8} {'F1':>8} {'DeltaF1':>8}")
    print("  " + "-" * 50)
    for ck, cn in CHECK_NAMES_SHORT.items():
        m = _ablation_metrics(proposed, excl=ck)
        flag = " <" if abs(m['F1']-base['F1'])>0.03 else ""
        print(f"  -{cn:>7} {m['TPR']:>8.4f} {m['FPR']:>8.4f} {m['F1']:>8.4f} {m['F1']-base['F1']:>+8.4f}{flag}")
    
    # --- Per-Attack ---
    for at, al in ATTACK_LABELS.items():
        sub = proposed[proposed['attack_type'].isin([at, 'Genuine'])]
        if sub.empty: continue
        base_at = _ablation_metrics(sub)
        print(f"\n  -- {al}: Full Model TPR={base_at['TPR']:.4f}  F1={base_at['F1']:.4f}")
        print(f"  {'Remove':>8} {'TPR':>8} {'DeltaTPR':>8} {'DeltaF1':>8}")
        print("  " + "-" * 40)
        for ck, cn in CHECK_NAMES_SHORT.items():
            m = _ablation_metrics(sub, excl=ck)
            flag = " <" if abs(m['TPR']-base_at['TPR'])>0.03 else ""
            print(f"  -{cn:>7} {m['TPR']:>8.4f} {m['TPR']-base_at['TPR']:>+8.4f} {m['F1']-base_at['F1']:>+8.4f}{flag}")


# =======================================================
#  TEXT: IDM Mitigation (RQ4)
# =======================================================

def rq4_mitigation(df):
    print("\n" + "=" * 95)
    print("  RQ4: IDM Mitigation")
    print("=" * 95)
    if 'mitigated_a' not in df.columns: print("  No data"); return
    p = df[df['det_name']=='P_Proposed']
    atk = p[(p['is_attack']==1) & (p['mitigated_a']!=0) & (p['mitigated_a']<0.5)]['mitigated_a']
    ben = p[(p['is_attack']==0) & (p['mitigated_a']!=0) & (p['mitigated_a']<0.5)]['mitigated_a']
    if len(atk)>0:
        print(f"\n  Attack BSMs (n={len(atk):,}): mean={atk.mean():.2f}+/-{atk.std():.2f}, median={atk.median():.2f}, min={atk.min():.2f}")
        print(f"  Reduction vs -8.0: {(8.0-abs(atk.mean()))/8.0*100:.0f}%")
    if len(ben)>0:
        print(f"  Benign BSMs (n={len(ben):,}): mean={ben.mean():.2f}+/-{ben.std():.2f}")


# =======================================================
#  LaTeX TABLES -> .tex files
# =======================================================

def latex_table_comparison(df, n_seeds, out_dir):
    """Table 3: Main comparison (tab:comparison)"""
    path = os.path.join(out_dir, 'tab_comparison.tex')
    total_bsm = len(df[df['det_name']=='P_Proposed'])
    
    lines = []
    lines.append(r'\begin{table}[t]')
    lines.append(r'\centering')
    if n_seeds > 1:
        lines.append(r'\caption{Aggregate detection performance (mean $\pm$ std over '
                     + str(n_seeds) + r' seeds, ${\sim}$' + f'{total_bsm:,}' + r' BSMs per detector per seed).}')
    else:
        lines.append(r'\caption{Aggregate detection performance (${\sim}$' + f'{total_bsm:,}' + r' BSM evaluations per detector).}')
    lines.append(r'\label{tab:comparison}')
    lines.append(r'\small')
    lines.append(r'\begin{tabular}{l|cccc}')
    lines.append(r'\hline')
    lines.append(r'\textbf{Method} & \textbf{TPR} & \textbf{FPR} & \textbf{Prec.} & \textbf{F1} \\')
    lines.append(r'\hline')
    
    for det in DET_ORDER:
        ps = metrics_per_seed(df, det)
        if not ps: continue
        lb = LABELS[det]
        tpr_m, tpr_s = ms([m['TPR'] for m in ps])
        fpr_m, fpr_s = ms([m['FPR'] for m in ps])
        pre_m, pre_s = ms([m['Precision'] for m in ps])
        f1_m,  f1_s  = ms([m['F1'] for m in ps])
        
        if det == 'P_Proposed':
            lb = r'\textbf{Proposed (Ours)}'
            if n_seeds > 1:
                lines.append(f'{lb} & $\\mathbf{{{tpr_m:.3f} \\pm {tpr_s:.3f}}}$ '
                             f'& $\\mathbf{{{fpr_m:.3f} \\pm {fpr_s:.3f}}}$ '
                             f'& $\\mathbf{{{pre_m:.3f} \\pm {pre_s:.3f}}}$ '
                             f'& $\\mathbf{{{f1_m:.3f} \\pm {f1_s:.3f}}}$ \\\\')
            else:
                lines.append(f'{lb} & \\textbf{{{tpr_m:.3f}}} & \\textbf{{{fpr_m:.3f}}} '
                             f'& \\textbf{{{pre_m:.3f}}} & \\textbf{{{f1_m:.3f}}} \\\\')
        elif det == 'B0_Naive':
            lines.append(f'{lb} & 0.000 & 0.000 & N/A & N/A \\\\')
        else:
            if n_seeds > 1:
                lines.append(f'{lb} & ${tpr_m:.3f} \\pm {tpr_s:.3f}$ '
                             f'& ${fpr_m:.3f} \\pm {fpr_s:.3f}$ '
                             f'& ${pre_m:.3f} \\pm {pre_s:.3f}$ '
                             f'& ${f1_m:.3f} \\pm {f1_s:.3f}$ \\\\')
            else:
                lines.append(f'{lb} & {tpr_m:.3f} & {fpr_m:.3f} & {pre_m:.3f} & {f1_m:.3f} \\\\')
    
    lines.append(r'\hline')
    lines.append(r'\end{tabular}%')
    lines.append(r'\end{table}')
    
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"    -> {path}")


def latex_table_mitigation(df, out_dir):
    """Table 4: IDM mitigation (tab:mitigation)"""
    path = os.path.join(out_dir, 'tab_mitigation.tex')
    if 'mitigated_a' not in df.columns: return
    
    p = df[df['det_name']=='P_Proposed']
    atk = p[(p['is_attack']==1) & (p['mitigated_a']!=0) & (p['mitigated_a']<0.5)]['mitigated_a']
    ben = p[(p['is_attack']==0) & (p['mitigated_a']!=0) & (p['mitigated_a']<0.5)]['mitigated_a']
    
    lines = []
    lines.append(r'\begin{table}[t]')
    lines.append(r'\centering')
    lines.append(r'\caption{IDM-bounded deceleration for EEBL-relevant BSMs.}')
    lines.append(r'\label{tab:mitigation}')
    lines.append(r'\small')
    lines.append(r'\begin{tabular}{@{}lccc@{}}')
    lines.append(r'\toprule')
    lines.append(r'\textbf{BSM Type} & \textbf{Mean} & \textbf{Median} & \textbf{Min} \\')
    lines.append(r'\midrule')
    if len(atk) > 0:
        lines.append(f'Attack ($n$={len(atk):,}) & ${atk.mean():.2f}$ m/s$^2$ '
                     f'& ${atk.median():.2f}$ m/s$^2$ & ${atk.min():.2f}$ m/s$^2$ \\\\')
    if len(ben) > 0:
        lines.append(f'Benign ($n$={len(ben):,}) & ${ben.mean():.2f}$ m/s$^2$ '
                     f'& ${ben.median():.2f}$ m/s$^2$ & ${ben.min():.2f}$ m/s$^2$ \\\\')
    lines.append(r'\midrule')
    lines.append(r'Unprotected EEBL & \multicolumn{3}{c}{$-8.0$ m/s$^2$ (emergency braking)} \\')
    lines.append(r'\bottomrule')
    lines.append(r'\end{tabular}')
    lines.append(r'\end{table}')
    
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"    -> {path}")


def latex_table_latency(df, out_dir):
    """New table: Detection latency with median (tab:latency)"""
    path = os.path.join(out_dir, 'tab_latency.tex')
    atk_types = {'FakeEEBLJustAttack': r'$\mathcal{A}_1$',
                 'FakeEEBLStopPositionUpdateAfterAttack': r'$\mathcal{A}_2$'}
    
    lines = []
    lines.append(r'\begin{table}[t]')
    lines.append(r'\centering')
    lines.append(r'\caption{Detection latency: time from first attack BSM to first detection per ego vehicle.}')
    lines.append(r'\label{tab:latency}')
    lines.append(r'\small')
    lines.append(r'\begin{tabular}{@{}llcccc@{}}')
    lines.append(r'\toprule')
    lines.append(r'\textbf{Detector} & \textbf{Attack} & \textbf{Mean (s)} & \textbf{Median (s)} & \textbf{BSMs Missed} & \textbf{Det. Rate} \\')
    lines.append(r'\midrule')
    
    for det in ['B1_Threshold', 'B2_VCADS', 'B3_F2MD', 'P_Proposed']:
        first_row = True
        for at, al in atk_types.items():
            sub = df[(df['det_name']==det) & (df['attack_type']==at)]
            if sub.empty: continue
            lats, bsms, n_det, n_total = [], [], 0, 0
            for (seed, hv), grp in sub.groupby(['seed','hv_id']):
                grp = grp.sort_values('time')
                n_total += 1
                det_rows = grp[grp['suspicious']==1]
                if len(det_rows) > 0:
                    n_det += 1
                    lats.append(det_rows['time'].iloc[0] - grp['time'].iloc[0])
                    bsms.append(len(grp[grp['time'] < det_rows['time'].iloc[0]]))
            
            det_label = LABELS.get(det, det) if first_row else ''
            rate = n_det / max(n_total, 1)
            if lats:
                lines.append(f'{det_label} & {al} & ${np.mean(lats):.2f} \\pm {np.std(lats):.2f}$ '
                             f'& ${np.median(lats):.2f}$ '
                             f'& ${np.mean(bsms):.1f} \\pm {np.std(bsms):.1f}$ & {rate:.2f} \\\\')
            else:
                lines.append(f'{det_label} & {al} & --- & --- & --- & 0.00 \\\\')
            first_row = False
        if det != 'P_Proposed':
            lines.append(r'\midrule')
    
    lines.append(r'\bottomrule')
    lines.append(r'\end{tabular}')
    lines.append(r'\end{table}')
    
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"    -> {path}")


def latex_table_ablation(df, out_dir):
    """New table: Per-check ablation with per-attack breakdown (tab:ablation)"""
    path = os.path.join(out_dir, 'tab_ablation.tex')
    proposed = df[df['det_name']=='P_Proposed'].copy()
    if proposed.empty: return
    
    # Base metrics
    base_all = _ablation_metrics(proposed)
    atk_types = {'FakeEEBLJustAttack': r'$\mathcal{A}_1$',
                 'FakeEEBLStopPositionUpdateAfterAttack': r'$\mathcal{A}_2$'}
    base_at = {}
    for at, al in atk_types.items():
        sub = proposed[proposed['attack_type'].isin([at, 'Genuine'])]
        base_at[at] = _ablation_metrics(sub)
    
    lines = []
    lines.append(r'\begin{table}[t]')
    lines.append(r'\centering')
    lines.append(r'\caption{Ablation study: impact of removing individual checks on overall and per-attack performance.}')
    lines.append(r'\label{tab:ablation}')
    lines.append(r'\small')
    lines.append(r'\begin{tabular}{@{}lcccccc@{}}')
    lines.append(r'\toprule')
    lines.append(r' & \multicolumn{2}{c}{\textbf{Overall}} & \multicolumn{2}{c}{$\mathcal{A}_1$} & \multicolumn{2}{c}{$\mathcal{A}_2$} \\')
    lines.append(r'\cmidrule(lr){2-3} \cmidrule(lr){4-5} \cmidrule(lr){6-7}')
    lines.append(r'\textbf{Configuration} & \textbf{F1} & $\Delta$\textbf{F1} & \textbf{TPR} & $\Delta$\textbf{TPR} & \textbf{TPR} & $\Delta$\textbf{TPR} \\')
    lines.append(r'\midrule')
    
    # Full model row
    a1k = 'FakeEEBLJustAttack'; a2k = 'FakeEEBLStopPositionUpdateAfterAttack'
    lines.append(f'Full Model & {base_all["F1"]:.3f} & --- '
                 f'& {base_at[a1k]["TPR"]:.3f} & --- '
                 f'& {base_at[a2k]["TPR"]:.3f} & --- \\\\')
    lines.append(r'\midrule')
    
    for ck, cn in CHECK_NAMES_SHORT.items():
        m_all = _ablation_metrics(proposed, excl=ck)
        df1 = m_all['F1'] - base_all['F1']
        
        sub_a1 = proposed[proposed['attack_type'].isin([a1k, 'Genuine'])]
        m_a1 = _ablation_metrics(sub_a1, excl=ck)
        dtpr_a1 = m_a1['TPR'] - base_at[a1k]['TPR']
        
        sub_a2 = proposed[proposed['attack_type'].isin([a2k, 'Genuine'])]
        m_a2 = _ablation_metrics(sub_a2, excl=ck)
        dtpr_a2 = m_a2['TPR'] - base_at[a2k]['TPR']
        
        lines.append(f'$-$Check~{cn} & {m_all["F1"]:.3f} & {df1:+.3f} '
                     f'& {m_a1["TPR"]:.3f} & {dtpr_a1:+.3f} '
                     f'& {m_a2["TPR"]:.3f} & {dtpr_a2:+.3f} \\\\')
    
    lines.append(r'\bottomrule')
    lines.append(r'\end{tabular}')
    lines.append(r'\end{table}')
    
    with open(path, 'w') as f:
        f.write('\n'.join(lines))
    print(f"    -> {path}")


# =======================================================
#  MAIN
# =======================================================

def main():
    results_dir = sys.argv[1] if len(sys.argv) > 1 else 'results'
    fig_dir = os.path.join(results_dir, 'figures')
    os.makedirs(fig_dir, exist_ok=True)

    print("=" * 95)
    print("  EEBL Multi-Seed Analysis + Paper Figures + LaTeX Tables")
    print("=" * 95)

    print("\n[1] Loading...")
    df, n_seeds = load_all(results_dir)
    df['is_attack'] = df['attack_type'].map(ATTACK_MAP).fillna(0).astype(int)
    print(f"  Rows: {len(df):,} | Seeds: {n_seeds} | Detectors: {sorted(df['det_name'].unique())}")

    df_main = df[df['det_name'].isin(DET_ORDER)]

    print("\n[2] Generating figures...")
    aucs = fig2_roc(df_main, fig_dir, n_seeds)
    fig3_per_attack(df_main, fig_dir, n_seeds)
    fig5_sensitivity(df_main, fig_dir, n_seeds)
    fig_ablation(df_main, fig_dir)
    fig_mitigation(df_main, fig_dir)

    print("\n[3] Generating LaTeX tables...")
    latex_table_comparison(df_main, n_seeds, fig_dir)
    latex_table_mitigation(df_main, fig_dir)
    latex_table_latency(df_main, fig_dir)
    latex_table_ablation(df_main, fig_dir)

    print("\n[4] Text analysis...")
    rq1_table(df_main, n_seeds, aucs)
    rq2_per_attack(df_main, n_seeds)
    analysis_latency(df_main)
    analysis_ablation(df_main)
    rq4_mitigation(df_main)

    print("\n" + "=" * 95)
    print(f"  Done!")
    print(f"  Figures -> {fig_dir}/*.png, *.pdf")
    print(f"  Tables  -> {fig_dir}/tab_*.tex")
    print("=" * 95)

if __name__ == '__main__':
    main()
