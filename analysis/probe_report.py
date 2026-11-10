"""Summarise the Q3 wording probe (taguri/probe.py output)."""
import gzip
import json
import sys
from collections import defaultdict

import numpy as np


def auroc(pos, neg):
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv)); ranks[order] = np.arange(1, len(allv) + 1)
    # average ranks for ties
    _, inv, cnt = np.unique(allv, return_inverse=True, return_counts=True)
    sums = np.zeros(len(cnt)); np.add.at(sums, inv, ranks)
    ranks = (sums / cnt)[inv]
    return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


rows = defaultdict(list)
for l in gzip.open(sys.argv[1], "rt"):
    r = json.loads(l)
    rows[r["variant"]].append(r)
print("| 寫法 | 無上下文 AUROC | 金標 lo≥0 | 金標 lo≥−4 | 每題非證據 lo≥0 | 每題非證據 lo≥−4 | 單輪重排 R@5 | 有上下文：金標 lo≥0 | 有上下文：非證據 lo≥0 | 金標 lo 中位數（無／有） |")
print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
for var, rs in rows.items():
    g = np.array([x["lpA"] - x["lpB"] for r in rs for x in r["noctx"] if x["gold"]])
    n = np.array([x["lpA"] - x["lpB"] for r in rs for x in r["noctx"] if not x["gold"]])
    cg = np.array([x["lpA"] - x["lpB"] for r in rs for x in r["ctx"] if x["gold"]])
    cn = np.array([x["lpA"] - x["lpB"] for r in rs for x in r["ctx"] if not x["gold"]])
    r5 = []
    for r in rs:
        ngold = len([x for x in r["ctx"] if x["gold"]])
        top = sorted(r["noctx"], key=lambda x: -(x["lpA"] - x["lpB"]))[:5]
        r5.append(sum(x["gold"] for x in top) / ngold)
    print(f"| {var} | {auroc(g, n):.3f} | {100 * (g >= 0).mean():.1f}% | {100 * (g >= -4).mean():.1f}% | {(n >= 0).sum() / len(rs):.2f} | {(n >= -4).sum() / len(rs):.2f} | "
          f"{100 * np.mean(r5):.1f} | {100 * (cg >= 0).mean():.1f}% | {100 * (cn >= 0).mean():.1f}% | {np.median(g):+.1f}／{np.median(cg):+.1f} |")
