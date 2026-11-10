"""S7a: choose the Chinese lexical layer on DRCD (CPU only). Runs every combination on the Traditional and the
Simplified copy and writes results/s7a-zh-lexical.json.

  python tools/s7a_zh_lexical.py --data /tmp/sag2poc-data --big-dict /path/to/dict.txt.big
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taguri.analyze import Analyzer  # noqa: E402
from taguri.index import Index, build  # noqa: E402
from evalkit import load_questions, load_split  # noqa: E402


def recall(ix, questions, qids, ks=(1, 5, 10)):
    hit = {k: 0 for k in ks}
    for q in qids:
        gold = questions[q]["gold_pids"][0]
        top = [ix.passage(r)["pid"] for r, _ in ix.search(questions[q]["question"], max(ks))]
        for k in ks:
            hit[k] += gold in top[:k]
    return {f"R@{k}": round(100 * hit[k] / len(qids), 2) for k in ks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--big-dict", required=True)
    ap.add_argument("--out", default="results/s7a-zh-lexical.json")
    a = ap.parse_args()
    lock = json.load(open("results/thresholds.lock.json"))
    combos = [("control: jieba default, no script normalisation", dict(zh_key=None, use_bigram=False, use_word=True))]
    for zk in ("t2s", "tw2sp", "s2twp"):
        for name, bg, wd in (("bigram", True, False), ("word", False, True), ("bigram+word", True, True)):
            kw = dict(zh_key=zk, use_bigram=bg, use_word=wd)
            if zk == "s2twp":
                kw["jieba_dict"] = a.big_dict
            combos.append((f"{zk} / {name}", kw))
    rows = []
    for label, kw in combos:
        row = {"setting": label}
        for ds in ("drcd-tw", "drcd-cn"):
            an = Analyzer(**kw)
            db = f"/tmp/s7a-{ds}-{label.replace(' ', '').replace('/', '-').replace(':', '').replace(',', '')}.db"
            t0 = time.time()
            info = build(os.path.join(a.data, ds, "corpus.jsonl"), db, an, log=lambda *_: None)
            ix = Index(db, an, lock.get("weights"))
            questions = load_questions(ds, a.data)
            row[ds] = recall(ix, questions, load_split(ds, "test", a.data))
            row[ds]["build_s"] = info["build_s"]
            row[ds]["db_mb"] = round(info["db_bytes"] / 1e6, 1)
            os.remove(db)
        row["gap_R@10"] = round(row["drcd-tw"]["R@10"] - row["drcd-cn"]["R@10"], 2)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    json.dump(rows, open(a.out, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
