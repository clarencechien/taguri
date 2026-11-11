"""Wording probe for the evidence question (Q3), run on the calibration half only.

For every question: candidates = round-0 candidate set (BM25F top-K + anchors). Each wording variant judges
  (a) every candidate with no evidence context, and
  (b) every gold passage and the 10 best non-gold candidates again with the OTHER gold passages as context
      (what the judge sees once the earlier hops have been found).
Output: one JSONL row per (variant, qid) with raw log-probs. Analysis is done offline (analysis/probe_report.py).
"""
import gzip
import json
import os
import time

from .analyze import Analyzer
from .decide import LLMDecider, Stats
from .run import get_index
from evalkit import load_questions, load_split


def run_probe(job, backend, lock, out_dir, flush):
    ds, split = job.get("dataset", "musique"), job.get("split", "calib")
    data_root = job.get("data_root", "/root/data")
    an = Analyzer(zh_key=lock.get("zh_key", "tw2sp"))
    ix = get_index(ds, data_root, "/tmp/idx" + data_root.replace("/", "_"), an, lock.get("weights"), tag="-probe")
    questions = load_questions(ds, data_root)
    qids = load_split(ds, split, data_root)[: int(job.get("limit") or 10 ** 9)]
    os.makedirs(out_dir, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor

    t0 = time.time()
    n_calls = 0
    with gzip.open(os.path.join(out_dir, "probe.jsonl.gz"), "wt") as f:
        for var in job["variants"]:  # e.g. "A-L1", "B-L2"
            q3, layout = var.split("-")
            dec = LLMDecider(backend, "en", q3, layout)

            def one(qid):
                q = {"qid": qid, **questions[qid]}
                st = Stats()
                rids = [r for r, _ in ix.search(q["question"], 50)]
                for a in ix.anchors(q["question"]):
                    sc = ix.search_keys(ix.query_keys(q["question"]), restrict=a["rids"]) if len(a["rids"]) > 5 else [(r, 0) for r in a["rids"]]
                    rids += [r for r, _ in sc[:5]]
                rids = list(dict.fromkeys(rids))
                gold = [ix.rid_of(p) for p in q["gold_pids"]]
                cands = [ix.passage(r) for r in rids]
                res = dec.evidence(q, [], cands, st)
                row = {"variant": var, "qid": qid, "noctx": [{"pid": c["pid"], "gold": c["rid"] in gold, "lpA": x["lpA"], "lpB": x["lpB"]} for c, x in zip(cands, res)], "ctx": []}
                nong = [c for c in cands if c["rid"] not in gold][:10]
                gp = [ix.passage(g) for g in gold]
                for g in gp:  # gold judged with the other gold passages as context
                    ev = [x for x in gp if x["rid"] != g["rid"]]
                    x = dec.evidence(q, ev, [g], st)[0]
                    row["ctx"].append({"pid": g["pid"], "gold": True, "lpA": x["lpA"], "lpB": x["lpB"]})
                if nong:  # non-gold judged with all gold as context
                    for c, x in zip(nong, dec.evidence(q, gp, nong, st)):
                        row["ctx"].append({"pid": c["pid"], "gold": False, "lpA": x["lpA"], "lpB": x["lpB"]})
                row["calls"] = st.calls
                return row

            with ThreadPoolExecutor(16) as ex:
                for row in ex.map(one, qids):
                    f.write(json.dumps(row) + "\n")
                    n_calls += row["calls"]
            print(f"  probe {var} done ({time.time() - t0:.0f}s)", flush=True)
            flush()
    return {"tag": job["tag"], "job_s": round(time.time() - t0, 1), "calls": n_calls}
