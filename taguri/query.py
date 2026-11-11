"""Ask one question against an existing index and print the ranked evidence. No gold labels needed.

  python -m taguri.query --db store/idx/mydocs.db --question "..." --judge llama --base-url http://127.0.0.1:8080
  python -m taguri.query --db store/idx/mydocs.db --question "..." --judge none          # lexical layer only
  python -m taguri.query --db ... --question "..." --lang zh --doc-level --json
"""
from __future__ import annotations

import argparse
import json
import time

from .analyze import Analyzer
from .decide import LLMDecider, LlamaBackend, SGLangBackend
from .index import Index
from .pipeline import Engine
from .run import load_lock, make_config


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--judge", default="llama", choices=["none", "llama", "sglang"])
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--tokenizer", help="tokenizer.json of the model (SGLang only)")
    ap.add_argument("--lang", default="en", help="en | zh (language of the corpus; decides the prompt language)")
    ap.add_argument("--doc-level", action="store_true")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--chars", type=int, default=300)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--llama-parallel", type=int, default=4)
    ap.add_argument("--lock", help="use this lock file instead of results/thresholds.lock.json")
    a = ap.parse_args()
    lock = load_lock(a.lock)
    zh = a.lang.startswith("zh")
    ix = Index(a.db, Analyzer(zh_key=lock.get("zh_key", "tw2sp")), lock.get("weights"))
    cfg = make_config("N0" if a.judge == "none" else "N1", lock)
    dec = None
    if a.judge != "none":
        backend = SGLangBackend(a.base_url, a.tokenizer) if a.judge == "sglang" else LlamaBackend(a.base_url, parallel=a.llama_parallel)
        dec = LLMDecider(backend, a.lang, lock.get("q3_variant_zh" if zh else "q3_variant", "A"), lock.get("layout", "L1"))
        if zh:
            for k, v in lock.get("zh", {}).items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
    t0 = time.perf_counter()
    r = Engine(ix, dec, doc_level=a.doc_level).run({"qid": "q", "question": a.question}, cfg)
    dt = time.perf_counter() - t0
    tr = r["trace"]
    lo = {x["pid"]: x["lo"] for x in tr["judged"]}
    rows = []
    best = {}
    for x in tr["judged"]:
        d = x["pid"].split("#")[0] if a.doc_level else x["pid"]
        if d not in best or x["lo"] > lo[best[d]]:
            best[d] = x["pid"]
    for rank, key in enumerate(r["retrieved"][: a.top], 1):
        pid = best.get(key, key)
        rid = ix.rid_of(pid) or ix.con.execute("SELECT rid FROM passages WHERE doc=? ORDER BY rid LIMIT 1", (key,)).fetchone()[0]
        p = ix.passage(rid)
        rows.append({"rank": rank, "id": key, "log_odds": round(lo[pid], 2) if pid in lo else None, "title": p["title"], "text": p["text"]})
    info = {"seconds": round(dt, 2), "judge_calls": tr["stats"]["calls"], "input_tokens": tr["stats"]["tokens"],
            "bridge_terms": [t for p in tr["picks"] for t in p.get("chosen", [])], "min_option_mass": tr["stats"]["min_mass"]}
    if a.json:
        print(json.dumps({"info": info, "results": rows}, ensure_ascii=False, indent=1))
        return
    for x in rows:
        s = "  --  " if x["log_odds"] is None else f"{x['log_odds']:+6.1f}"
        print(f"{x['rank']:>2}. [{s}] {x['title']}\n      {' '.join(x['text'].split())[:a.chars]}")
    print("\n" + json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
