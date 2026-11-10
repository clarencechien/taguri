"""Score engine runs and compare them, question by question, with each other or with reference/ scores.

  python analysis/compare.py score  --runs out/s6 --tag musique-dev-N1 --dataset musique --split dev
  python analysis/compare.py table  --spec analysis/s6.json
Used as a library by the per-stage report scripts.
"""
from __future__ import annotations

import gzip
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evalkit import aggregate, load_questions, load_run, load_scores, load_split, paired_bootstrap, score_run  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_Q = {}


def questions(ds, root=None):
    key = (ds, root)
    if key not in _Q:
        _Q[key] = load_questions(ds, root or os.path.join(ROOT, "data"))
    return _Q[key]


def scores_of(run_dir, ds, split, root=None):
    """-> ({qid: metrics}, qids)"""
    root = root or os.path.join(ROOT, "data")
    qids = load_split(ds, split, root)
    return score_run(questions(ds, root), load_run(os.path.join(run_dir, "run.jsonl")), qids), qids


def ref(ds, name):
    return load_scores(os.path.join(ROOT, "reference", ds, f"{name}.jsonl"))


def merged(parts):
    """parts: [(scores, qids)] -> one (scores, qids) with dataset-prefixed qids, for pooled (dev-400) comparisons."""
    sc, ids = {}, []
    for i, (s, q) in enumerate(parts):
        for x in q:
            sc[f"{i}:{x}"] = s[x]
            ids.append(f"{i}:{x}")
    return sc, ids


def agg(scores, qids):
    return {k: round(v, 2) for k, v in aggregate(scores, qids).items()}


def delta(a, b, qids, metric):
    r = paired_bootstrap(a, b, qids, metric)
    return {"delta": round(float(r["delta"]), 2), "lo": round(float(r["ci_low"]), 2), "hi": round(float(r["ci_high"]), 2)}


def fmt(d):
    return f"{d['delta']:+.2f}（{d['lo']:+.2f}，{d['hi']:+.2f}）"


def traces(run_dir):
    with gzip.open(os.path.join(run_dir, "trace.jsonl.gz"), "rt") as f:
        return [json.loads(l) for l in f]


def call_stats(run_dir):
    t = traces(run_dir)
    calls = sorted(x["stats"]["calls"] for x in t)
    return {"median": statistics.median(calls), "p90": calls[int(0.9 * (len(calls) - 1))], "mean": round(sum(calls) / len(calls), 1),
            "tokens_per_q": round(sum(x["stats"]["tokens"] for x in t) / len(t)),
            "rounds_mean": round(sum(max((r["round"] for r in x["rounds"]), default=0) for x in t) / len(t), 2)}


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score"])
    ap.add_argument("--runs"); ap.add_argument("--tag"); ap.add_argument("--dataset"); ap.add_argument("--split")
    ap.add_argument("--vs", nargs="*", default=[])
    a = ap.parse_args()
    s, q = scores_of(os.path.join(a.runs, a.tag), a.dataset, a.split)
    print(a.tag, agg(s, q))
    for v in a.vs:
        r = ref(a.dataset, v)
        print("  −", v, {m: fmt(delta(s, r, q, m)) for m in ("R@5", "R@10", "AE@10")})
