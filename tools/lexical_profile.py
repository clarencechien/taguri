"""Where does the CPU time of one question go? (TODO B1.)  No GPU: the judge is replayed from a saved trace.

The replay decider answers every judge call from a previous run's trace.jsonl.gz (log-odds per passage, the term
chosen in each pick), so the pipeline walks nearly the same path as the real run and issues the same lexical
queries. Each Index method is timed. The retrieved lists are written out, so two versions of the lexical code can
be compared for identical output.

usage: lexical_profile.py --db <index.db> --data-root <dir> --dataset enterprise --split recall470 \
           --trace <trace.jsonl.gz> --n 40 [--doc-level] [--out run.jsonl] [--types a,b] [--threads 4]
"""
import argparse, collections, gzip, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evalkit import load_questions, load_split
from taguri.analyze import Analyzer
from taguri.index import Index
from taguri.pipeline import Engine
from taguri.run import load_lock, make_config


class ReplayDecider:
    """Answers from a saved trace. Unknown passages get a clear 'no'; unknown pick groups keep the first option."""

    def __init__(self, traces):
        self.tr = traces
        self.miss = collections.Counter()

    def _j(self, q):
        t = self.tr[q["qid"]]
        if "_by_pid" not in t:
            t["_by_pid"] = {j["pid"]: j for j in t["judged"]}
            t["_seen"] = set()
            t["_picks"] = {tuple(g): lp for p in t["picks"] for g, lp in zip(p.get("groups", []), p.get("lp", []))}
        return t

    def evidence(self, q, evidence, cands, stats):
        t = self._j(q)
        out = []
        for c in cands:
            stats.calls += 1
            j = t["_by_pid"].get(c["pid"])
            if j is None:
                self.miss["evidence"] += 1
                lo = -20.0
            else:
                lo = j["lo"] if c["pid"] in t["_seen"] else j.get("lo0", j["lo"])  # first verdict first, the final one afterwards
                t["_seen"].add(c["pid"])
            out.append({"lpA": 0.0, "lpB": 0.0, "lo": lo, "mass": 1.0})
        return out

    def pick(self, q, evidence, terms, stats):
        stats.calls += 1
        lp = self._j(q)["_picks"].get(tuple(terms))
        if lp is None:
            self.miss["pick"] += 1
            return [-i * 1e-6 for i in range(len(terms))]
        return lp

    def none_label(self):
        return "None of these"


def timed(ix, T):
    """Wrap the Index methods that touch SQLite with wall-clock timers (nested calls are counted in both)."""
    def wrap(name, key=None):
        f = getattr(ix, name)

        def g(*a, **k):
            t0 = time.perf_counter()
            try:
                return f(*a, **k)
            finally:
                kk = key(a, k) if key else name
                T[kk][0] += 1; T[kk][1] += time.perf_counter() - t0
        setattr(ix, name, g)
    wrap("search_keys", lambda a, k: "search_keys(restrict)" if (len(a) > 2 and a[2] is not None) or k.get("restrict") is not None else "search_keys(full)")
    for n in ("fused_search", "anchors", "phrase_rids", "phrase_df", "passage"):
        wrap(n)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True); ap.add_argument("--data-root", required=True)
    ap.add_argument("--dataset", default="enterprise"); ap.add_argument("--split", default="recall470")
    ap.add_argument("--trace", required=True); ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--config", default="N1"); ap.add_argument("--doc-level", action="store_true")
    ap.add_argument("--types"); ap.add_argument("--out"); ap.add_argument("--threads", type=int, default=1); ap.add_argument("--every", type=int, default=1, help="take every k-th question of the split")
    a = ap.parse_args()
    lock = load_lock(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "thresholds.lock.json"))
    qs = load_questions(a.dataset, a.data_root); qids = load_split(a.dataset, a.split, a.data_root)
    if a.types:
        qids = [q for q in qids if qs[q]["type"] in a.types.split(",")]
    traces = {}
    with gzip.open(a.trace, "rt") as f:
        for line in f:
            r = json.loads(line); traces[r["qid"]] = r
    qids = [q for q in qids if q in traces][::a.every][:a.n]
    ix = Index(a.db, Analyzer(zh_key=lock.get("zh_key", "tw2sp")), lock.get("weights"))
    T = collections.defaultdict(lambda: [0, 0.0])
    timed(ix, T)
    dec = ReplayDecider(traces)
    eng = Engine(ix, dec, doc_level=a.doc_level)
    cfg = make_config(a.config, lock)
    def one(q):
        t0 = time.perf_counter()
        r = eng.run(qs[q], cfg)
        return time.perf_counter() - t0, r["trace"]["stats"]["calls"], {"qid": q, "retrieved": r["retrieved"]}

    t_all = time.perf_counter()
    if a.threads > 1:  # the method timers are not exact across threads; the per-question times are
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(a.threads) as ex:
            res = list(ex.map(one, qids))
    else:
        res = [one(q) for q in qids]
    t_all = time.perf_counter() - t_all
    walls, calls, rows = sorted(x[0] for x in res), [x[1] for x in res], [x[2] for x in res]
    n = len(walls)
    print(f"{n} questions, {a.threads} thread(s), {t_all:.1f}s in all ({t_all / n:.2f}s per question of throughput). per question: median {walls[n // 2]:.2f}s  p90 {walls[int(n * 0.9)]:.2f}s  mean {sum(walls) / n:.2f}s  max {walls[-1]:.2f}s")
    print(f"replayed judge calls per question: mean {sum(calls) / n:.0f}; replay misses: {dict(dec.miss)}")
    print("| Index 方法 | 每題呼叫次數 | 每題秒數 | 每次毫秒 |\n|---|---:|---:|---:|")
    for k, (c, s) in sorted(T.items(), key=lambda kv: -kv[1][1]):
        print(f"| `{k}` | {c / n:.1f} | {s / n:.2f} | {1000 * s / max(c, 1):.1f} |")
    if a.out:
        with open(a.out, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
