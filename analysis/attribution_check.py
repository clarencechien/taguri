"""Recompute the paired EnterpriseRAG comparisons from per-question score files.

usage: attribution_check.py <data root with enterprise/questions.jsonl> [taguri_n1_eg2 score file]
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evalkit import load_questions, load_split
from evalkit.bootstrap import paired_bootstrap

ROOT = sys.argv[1]
REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reference", "enterprise")
qs = load_questions("enterprise", ROOT); qids = load_split("enterprise", "recall470", ROOT)
ORDER = ["basic", "semantic", "intra_document_reasoning", "project_related", "constrained", "conflicting_info", "completeness", "miscellaneous"]
ZH = dict(zip(ORDER, ["基本檢索", "語意檢索", "文件內推理", "專案相關", "限定條件", "資訊衝突", "完整性", "其他"]))


def load(name):
    p = name if os.path.exists(name) else os.path.join(REF, name)
    return {r["qid"]: r for r in map(json.loads, open(p))}


S = {k: load(f) for k, f in [("jev", "sag2_jev.jsonl"), ("bm25", "bm25_upstream.jsonl"), ("n0", "taguri_n0.jsonl"), ("n1", "taguri_n1.jsonl")]}
S["eg"] = load(sys.argv[2] if len(sys.argv) > 2 else "taguri_n1_eg2.jsonl")
by = {t: [q for q in qids if qs[q]["type"] == t] for t in ORDER}
by["all"] = qids; ZH["all"] = "整體"


def mean(s, qq, m="R@10"):
    return 100 * sum(s[q][m] for q in qq) / len(qq)


def d(a, b, qq, m="R@10"):
    r = paired_bootstrap(S[a], S[b], qq, metric=m)
    return f"{r['delta']:+.2f}（{r['ci_low']:+.2f}，{r['ci_high']:+.2f}）"


print("| 題型 | 題數 | SAG2＋Jev | 上游 BM25 | N0 | N1 | N1 − SAG2＋Jev | N0 − 上游 BM25 |\n|---|---:|---:|---:|---:|---:|---|---|")
for t in ["all"] + ORDER:
    qq = by[t]
    print(f"| {ZH[t]} | {len(qq)} | " + " | ".join(f"{mean(S[k], qq):.2f}" for k in ("jev", "bm25", "n0", "n1")) + f" | {d('n1', 'jev', qq)} | {d('n0', 'bm25', qq)} |")

print("\n含 EG2：\n| 題型 | 題數 | N1＋EG2 | N1 | SAG2＋Jev | N1＋EG2 − SAG2＋Jev | N1＋EG2 − N1 |\n|---|---:|---:|---:|---:|---|---|")
for t in ["all"] + ORDER:
    qq = [q for q in by[t] if q in S["eg"]]
    if qq:
        print(f"| {ZH[t]} | {len(qq)} | {mean(S['eg'], qq):.2f} | {mean(S['n1'], qq):.2f} | {mean(S['jev'], qq):.2f} | {d('eg', 'jev', qq)} | {d('eg', 'n1', qq)} |")
qq = [q for q in qids if q in S["eg"]]
for m in ("R@1", "R@5", "AE@10"):
    print(m, f"N1+EG2 {mean(S['eg'], qq, m):.2f}  N1 {mean(S['n1'], qq, m):.2f}  Jev {mean(S['jev'], qq, m):.2f}  EG−Jev {d('eg', 'jev', qq, m)}  N1−Jev {d('n1', 'jev', qq, m)}")
