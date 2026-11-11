"""S10 tables (document-level R@10 by question type). usage: s10_report.py <runs dir> <data root with enterprise/>"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare import agg, call_stats, delta, fmt
from evalkit import load_questions, load_run, load_split, score_run

D, ROOT = sys.argv[1], sys.argv[2]
qs = load_questions("enterprise", ROOT); qids = load_split("enterprise", "recall470", ROOT)
ORDER = ["basic", "semantic", "intra_document_reasoning", "project_related", "constrained", "conflicting_info", "completeness", "miscellaneous"]
ZH = dict(zip(ORDER, ["基本檢索", "語意檢索", "文件內推理", "專案相關", "限定條件", "資訊衝突", "完整性", "其他"]))
REF = {"basic": (77.7, 48.6, 86.86), "semantic": (43.2, 24.8, 58.40), "intra_document_reasoning": (90.0, 57.5, 100.0), "project_related": (65.5, 49.2, 83.58),
       "constrained": (85.0, 83.3, 96.67), "conflicting_info": (82.5, 55.0, 92.50), "completeness": (46.5, 33.4, 76.24), "miscellaneous": (90.0, 75.0, 100.0), "all": (68.4, 46.0, 81.10)}
runs = {}
for c in ("N0", "N1", "N1+EG2"):
    p = os.path.join(D, f"enterprise-{c}")
    if os.path.exists(os.path.join(p, "run.jsonl")):
        runs[c] = score_run(qs, load_run(os.path.join(p, "run.jsonl")), qids)
by = {t: [q for q in qids if qs[q]["type"] == t] for t in ORDER}
print("| 題型 | 題數 | " + " | ".join(runs) + " | 參考：BM25 | 向量檢索 | SAG2＋Jev |\n|---|---:|" + "---:|" * (len(runs) + 3))
for t in ORDER + ["all"]:
    qq = qids if t == "all" else by[t]
    print(f"| {ZH.get(t, '**整體**')} | {len(qq)} | " + " | ".join(f"{agg(s, qq)['R@10']:.2f}" for s in runs.values()) + " | " + " | ".join(f"{x:.1f}" for x in REF[t]) + " |")
print("\n整體其他指標:", {c: {k: v for k, v in agg(s, qids).items() if k in ("R@1", "R@5", "R@10", "AE@10")} for c, s in runs.items()})
pairs = [("N1", "N0"), ("N1+EG2", "N1"), ("N1+EG2", "N0")]
print("\n| 比較（ΔR@10） | " + " | ".join(ZH[t] for t in ORDER) + " | 整體 |\n|---|" + "---|" * (len(ORDER) + 1))
for a, b in pairs:
    if a in runs and b in runs:
        print(f"| {a} − {b} | " + " | ".join(fmt(delta(runs[a], runs[b], by[t], "R@10")) for t in ORDER) + " | " + fmt(delta(runs[a], runs[b], qids, "R@10")) + " |")
for c in runs:
    if c != "N0":
        p = os.path.join(D, f"enterprise-{c}")
        print(c, call_stats(p), {k: v for k, v in json.load(open(os.path.join(p, "summary.json"))).items() if k in ("wall_s", "fresh_calls", "fresh_tokens", "failed_questions", "eg2_query_s", "eg2_queries", "min_option_mass")})
