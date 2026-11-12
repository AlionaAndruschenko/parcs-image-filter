#!/usr/bin/env python3
"""Будує графік "час виконання vs кількість воркерів" з results.csv.

Приклад:  python3 tools/plot_results.py results/results.csv results/chart.png
Потрібно: pip install matplotlib
"""
import csv
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

BLUE, GRAY, INK, INK2, SURFACE = '#2a78d6', '#8f8e89', '#0b0b0b', '#52514e', '#fcfcfb'


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else 'results/results.csv'
    out = sys.argv[2] if len(sys.argv) > 2 else 'results/chart.png'
    title = sys.argv[3] if len(sys.argv) > 3 else 'Паралельна фільтрація (Гаусс): час vs кількість воркерів'
    rows = list(csv.DictReader(open(src)))
    par = [r for r in rows if r['mode'] == 'par']
    seq = [r for r in rows if r['mode'] == 'seq']
    n = [int(r['workers']) for r in par]
    t = [float(r['compute_s']) for r in par]

    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ideal = [t[0] / k for k in n]
    ax.plot(n, ideal, color=GRAY, lw=1.5, ls='--', label='Ідеальне прискорення (T1 / N)')
    ax.plot(n, t, color=BLUE, lw=2, marker='o', ms=8, mec=SURFACE, mew=2, label='Паралельний алгоритм (PARCS)')
    if seq:
        ts = float(seq[0]['compute_s'])
        ax.axhline(ts, color=INK2, lw=1, ls=':', label='Послідовний алгоритм (master)')
    for x, y in zip(n, t):
        ax.annotate('%.2f с' % y, (x, y), textcoords='offset points', xytext=(0, 10),
                    ha='center', fontsize=9, color=INK)
    ax.set_xticks(n)
    ax.set_xlabel('Кількість воркерів N', color=INK2)
    ax.set_ylabel('Час обчислення, с', color=INK2)
    ax.set_title(title, color=INK, fontsize=11, loc='left')
    ax.set_ylim(0, max(t + ([float(seq[0]['compute_s'])] if seq else [])) * 1.18)
    ax.grid(axis='y', color='#e4e3df', lw=0.8)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color('#c9c8c2')
    ax.tick_params(colors=INK2)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out, facecolor=SURFACE)
    print('Saved', out)


if __name__ == '__main__':
    main()
