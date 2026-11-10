"""Re-rank logged judgments offline under both Q8 orderings (no GPU). usage: outmode.py <run_dir> <dataset> <split> <tau>"""
import gzip, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taguri.analyze import Analyzer
from taguri.index import Index
from taguri.run import get_index
from evalkit import load_questions, load_split, score_run, aggregate

def rerank(run_dir, ds, split, tau, idx_dir="/tmp/sag2poc-idx"):
    lock = json.load(open("results/thresholds.lock.json"))
    ix = get_index(ds, "data", idx_dir, Analyzer(), lock["weights"], log=lambda *_: None)
    qs = load_questions(ds); qids = load_split(ds, split)
    rows = [json.loads(l) for l in gzip.open(os.path.join(run_dir, "trace.jsonl.gz"), "rt")]
    out = {}
    for mode in ("all_logodds", "pool_then_bm25"):
        run = {}
        for r in rows:
            base = [ix.passage(x)["pid"] for x, _ in ix.search(qs[r["qid"]]["question"], 100)]
            o = [x["pid"] for x in sorted(r["judged"], key=lambda x: -x["lo"]) if mode == "all_logodds" or x["lo"] >= tau]
            run[r["qid"]] = o + [p for p in base if p not in o]
        a = aggregate(score_run(qs, run, qids))
        out[mode] = {k: round(a[k], 2) for k in ("R@5", "R@10", "AE@10")}
    return out

if __name__ == "__main__":
    print(json.dumps(rerank(sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4]))))
