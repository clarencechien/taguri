"""S6 tables: paired comparisons on dev (MuSiQue 300 + 2Wiki 100). usage: s6_report.py <dir with s6 runs>"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare import agg, call_stats, delta, fmt, merged, ref, scores_of

D = sys.argv[1]
DS = [("musique", "dev"), ("2wikimultihopqa", "dev")]

def load(cfg):
    parts = []
    for ds, sp in DS:
        p = os.path.join(D, f"{ds}-{sp}-{cfg}")
        if not os.path.exists(p):
            return None
        parts.append(scores_of(p, ds, sp))
    return parts

def refs(name):
    return [(ref(ds, name), scores_of.__globals__["load_split"](ds, sp, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))) for ds, sp in DS]

def row(name, parts):
    m, q = merged(parts)
    a = [agg(*p) for p in parts]; al = agg(m, q)
    return f"| {name} | {a[0]['R@5']:.2f} | {a[0]['R@10']:.2f} | {a[0]['AE@10']:.2f} | {a[1]['R@5']:.2f} | {a[1]['AE@10']:.2f} | **{al['R@5']:.2f}** | {al['R@10']:.2f} | {al['AE@10']:.2f} |"

runs = {c: load(c) for c in ("N0", "N1", "N1c", "N2", "N2c", "N3", "N3c", "N1+EG2", "N1c+EG2", "N1-rj30-DEVIATION")}
R = {n: refs(n) for n in ("bm25", "b0", "sag2_jev")}
print("| 設定 | MuSiQue R@5 | R@10 | AE@10 | 2Wiki R@5 | AE@10 | dev 400 R@5 | R@10 | AE@10 |\n|---|---:|---:|---:|---:|---:|---:|---:|---:|")
for n, lab in (("bm25", "上游 BM25"), ("b0", "B0"), ("sag2_jev", "SAG2＋Jev")):
    print(row(lab, R[n]))
for c, p in runs.items():
    if p: print(row(c, p))
def cmp(a, b, la, lb):
    out = [f"| {la} − {lb} |"]
    for parts_a, parts_b in ((a[0:1], b[0:1]), (a[1:2], b[1:2]), (a, b)):
        ma, q = merged(parts_a); mb, _ = merged(parts_b)
        out.append(" " + fmt(delta(ma, mb, q, "R@5")) + " | " + fmt(delta(ma, mb, q, "AE@10")) + " |")
    print("".join(out))
print("\n| 比較 | MuSiQue ΔR@5 | ΔAE@10 | 2Wiki ΔR@5 | ΔAE@10 | dev 400 ΔR@5 | ΔAE@10 |\n|---|---|---|---|---|---|---|")
pairs = [("N0", "bm25"), ("N1", "b0"), ("N1c", "b0"), ("N1", "N1c"), ("N2", "N1"), ("N2c", "N1c"), ("N3", "N1"), ("N3", "N2"), ("N1+EG2", "N1"), ("N1c+EG2", "N1c"), ("N1-rj30-DEVIATION", "N1"), ("N1-rj30-DEVIATION", "b0")]
for a, b in pairs:
    A = runs.get(a) or R.get(a); B = runs.get(b) or R.get(b)
    if A and B: cmp(A, B, a, b)
print("\n| 設定 | 每題判斷次數 中位數 | 第 90 百分位 | 平均 | 每題輸入 token | 平均擴展輪數 |\n|---|---:|---:|---:|---:|---:|")
for c in runs:
    for ds, sp in DS:
        p = os.path.join(D, f"{ds}-{sp}-{c}")
        if os.path.exists(p) and c != "N0":
            s = call_stats(p); print(f"| {c}（{ds}） | {s['median']} | {s['p90']} | {s['mean']} | {s['tokens_per_q']} | {s['rounds_mean']} |")
