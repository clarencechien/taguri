"""Run one configuration on one dataset split.

  python -m taguri.run --config N1 --dataset musique --split dev --judge sglang --base-url http://127.0.0.1:30000 \
      --tokenizer /hf/.../tokenizer.json --out out/musique-dev-N1
  python -m taguri.run --config N0 --dataset musique --split dev            # CPU only
  python -m taguri.run --config N1 --dataset musique --split calib --judge oracle   # CPU-only pipeline bound
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor

from .analyze import Analyzer
from .decide import LLMDecider, OracleDecider, SGLangBackend
from .index import Index, build
from .pipeline import CONFIGS, Config, Engine

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_lock(path=None):
    path = path or os.path.join(ROOT, "results", "thresholds.lock.json")
    return json.load(open(path)) if os.path.exists(path) else {}


def make_config(name, lock=None, **over):
    base = name.split("+")[0]
    kw = dict(CONFIGS[base])
    lock = lock or {}
    for k in ("tau", "anchor_bonus", "out_mode", "beta", "chunk", "rejudge_each", "pick_none", "min_pool", "term_rank", "n_cand", "rounds_n1"):
        if k in lock:
            kw[k] = lock[k]
    if "+EG2" in name:
        kw["dense"] = True
    kw.update({k: v for k, v in over.items() if v is not None})
    return Config(name=name, **kw)


def get_index(dataset, data_dir, idx_dir, analyzer, weights=None, doc_field=None, tag="", log=print, workers=1):
    os.makedirs(idx_dir, exist_ok=True)
    db = os.path.join(idx_dir, f"{dataset}{tag}.db")
    if not os.path.exists(db):
        info = build(os.path.join(data_dir, dataset, "corpus.jsonl"), db, analyzer, doc_field=doc_field, log=log, workers=workers)
        log(f"built index {db}: {info}")
        json.dump(info, open(db + ".json", "w"))
    return Index(db, analyzer, weights)


def run_split(engine, cfg, questions, qids, out_dir, workers=16, log=print, flush=None):
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    rows = [None] * len(qids)

    def one(i):
        q = {"qid": qids[i], **questions[qids[i]]}
        try:
            rows[i] = engine.run(q, cfg)
        except Exception as e:  # noqa: BLE001  one bad question must not lose the whole run: fall back to the lexical order and flag it
            log(f"  !! {qids[i]} failed: {e!r}")
            from .pipeline import Config

            rows[i] = engine.run(q, Config(name="fallback-N0", anchor_bonus=cfg.anchor_bonus))
            rows[i]["trace"]["error"] = repr(e)
        return i

    done = 0
    with ThreadPoolExecutor(workers) as ex:
        for _ in ex.map(one, range(len(qids))):
            done += 1
            if done % 50 == 0:
                log(f"  [{cfg.name}] {done}/{len(qids)} ({time.time() - t0:.0f}s)")
                if flush:
                    flush()
    wall = time.time() - t0
    with open(os.path.join(out_dir, "run.jsonl"), "w") as f:
        for r in rows:
            f.write(json.dumps({"qid": r["qid"], "retrieved": r["retrieved"]}) + "\n")
    with gzip.open(os.path.join(out_dir, "trace.jsonl.gz"), "wt") as f:
        for r in rows:
            f.write(json.dumps({"qid": r["qid"], **r["trace"]}) + "\n")
    calls = [r["trace"]["stats"]["calls"] for r in rows]
    st = lambda k: sum(r["trace"]["stats"][k] for r in rows)  # noqa: E731
    summ = {"config": cfg.__dict__, "n": len(qids), "wall_s": round(wall, 1),
            "calls_median": statistics.median(calls), "calls_p90": sorted(calls)[int(0.9 * (len(calls) - 1))], "calls_mean": sum(calls) / len(calls),
            "tokens_per_q": st("tokens") / len(qids), "fresh_calls": st("fresh"), "fresh_tokens": st("fresh_tokens"),
            "radix_cached_tokens": st("radix_cached"), "judge_wait_s": round(st("judge_s"), 1),
            "min_option_mass": min(r["trace"]["stats"]["min_mass"] for r in rows), "failed_questions": sum(1 for r in rows if r["trace"].get("error"))}
    json.dump(summ, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    if flush:
        flush()
    return summ


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="N0")
    ap.add_argument("--dataset", default="musique")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--judge", default="none", choices=["none", "sglang", "oracle"])
    ap.add_argument("--base-url", default="http://127.0.0.1:30000")
    ap.add_argument("--tokenizer")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "data"))
    ap.add_argument("--idx-dir", default="/tmp/taguri-idx")
    ap.add_argument("--out")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--tau", type=float)
    ap.add_argument("--out-mode")
    ap.add_argument("--anchor-bonus", type=float)
    ap.add_argument("--weights", help='json, e.g. {"title": 2}')
    ap.add_argument("--no-lock", action="store_true")
    a = ap.parse_args()

    from evalkit import aggregate, load_questions, load_split, score_run

    lock = {} if a.no_lock else load_lock()
    weights = json.loads(a.weights) if a.weights else lock.get("weights")
    an = Analyzer(zh_key=lock.get("zh_key", "tw2sp"))
    ix = get_index(a.dataset, a.data_dir, a.idx_dir, an, weights)
    questions = load_questions(a.dataset, a.data_dir) if a.data_dir else load_questions(a.dataset)
    qids = load_split(a.dataset, a.split, a.data_dir)
    cfg = make_config(a.config, lock, tau=a.tau, out_mode=a.out_mode, anchor_bonus=a.anchor_bonus)
    dec = None
    if a.judge == "sglang":
        dec = LLMDecider(SGLangBackend(a.base_url, a.tokenizer), a.lang)
    elif a.judge == "oracle":
        gold = {}

        def gold_rids(q):
            g = gold.get(q["qid"])
            if g is None:
                flat = [p for item in q["gold_pids"] for p in ([item] if isinstance(item, str) else item)]
                g = gold[q["qid"]] = {ix.rid_of(p) for p in flat}
            return g

        def pick_hook(q, evidence, terms):
            have = {p["rid"] for p in evidence}
            miss = [ix.passage(r) for r in gold_rids(q) if r not in have]
            return [sum((t.lower() in (p["title"] + " " + p["text"]).lower()) for p in miss) for t in terms]

        dec = OracleDecider(gold_rids, pick_hook)
    eng = Engine(ix, dec)
    out = a.out or f"/tmp/taguri-out/{a.dataset}-{a.split}-{a.config}-{a.judge}"
    summ = run_split(eng, cfg, questions, qids, out, workers=a.workers if a.judge == "sglang" else 4)
    run = {json.loads(l)["qid"]: json.loads(l)["retrieved"] for l in open(os.path.join(out, "run.jsonl"))}
    agg = aggregate(score_run(questions, run, qids))
    print(json.dumps({"out": out, "calls_median": summ["calls_median"], **{k: round(v, 2) for k, v in agg.items()}}))


if __name__ == "__main__":
    main()
