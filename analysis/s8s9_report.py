"""S8 (MuSiQue test) and S9 (MultiHop-RAG) tables. usage: s8s9_report.py <dir with runs>"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compare import agg, call_stats, delta, fmt, questions, ref, scores_of, traces

D = sys.argv[1]
M = ("R@1", "R@2", "R@5", "R@10", "AE@5", "AE@10")
def table(ds, split, tag, refs, types):
    s, q = scores_of(os.path.join(D, tag), ds, split)
    qs = questions(ds)
    print(f"\n## {ds} {split} (n={len(q)})\n| 方法 | " + " | ".join(M) + " |\n|---|" + "---:|" * len(M))
    a = agg(s, q); print("| **Taguri** | " + " | ".join(f"{a[m]:.2f}" for m in M) + " |")
    for name, lab in refs:
        r = ref(ds, name) if isinstance(name, str) else name
        a = agg(r, q); print(f"| {lab} | " + " | ".join(f"{a[m]:.2f}" for m in M) + " |")
    print("\n| Taguri − | " + " | ".join(M) + " |\n|---|" + "---|" * len(M))
    for name, lab in refs:
        r = ref(ds, name) if isinstance(name, str) else name
        print(f"| {lab} | " + " | ".join(fmt(delta(s, r, q, m)) for m in M) + " |")
    print("\n| 題型 | 題數 | Taguri R@5 | " + " | ".join(f"{lab} R@5" for _, lab in refs) + " | Taguri AE@10 |\n|---|---:|---:|" + "---:|" * (len(refs) + 1))
    for t in types:
        qq = [x for x in q if qs[x]["type"] == t]
        print(f"| {t} | {len(qq)} | {agg(s, qq)['R@5']:.2f} | " + " | ".join(f"{agg(ref(ds, n) if isinstance(n, str) else n, qq)['R@5']:.2f}" for n, _ in refs) + f" | {agg(s, qq)['AE@10']:.2f} |")
    print("\ncalls:", call_stats(os.path.join(D, tag)), json.load(open(os.path.join(D, tag, "summary.json")))["wall_s"])
    t = traces(os.path.join(D, tag))
    print("option mass min:", min(x["stats"]["min_mass"] for x in t))

if os.path.exists(os.path.join(D, "musique-test-N1")):
    table("musique", "test", "musique-test-N1", [("sag2_jev", "SAG2＋Jev"), ("sag2_jina", "SAG2＋Jina"), ("bm25", "上游 BM25")], ("2hop", "3hop", "4hop"))
if os.path.exists(os.path.join(D, "multihop-rag-sample300-N1")):
    n0, _ = scores_of(os.path.join(D, "multihop-rag-sample300-N0"), "multihop-rag", "sample300")
    table("multihop-rag", "sample300", "multihop-rag-sample300-N1", [("b0", "B0"), ("bm25", "上游 BM25"), (n0, "N0")], ("comparison_query", "inference_query", "temporal_query"))
    b0 = ref("multihop-rag", "b0"); bm = ref("multihop-rag", "bm25"); q = scores_of(os.path.join(D, "multihop-rag-sample300-N0"), "multihop-rag", "sample300")[1]
    print("B0 − BM25 R@10:", fmt(delta(b0, bm, q, "R@10")), "| N0 − BM25 R@10:", fmt(delta(n0, bm, q, "R@10")))
