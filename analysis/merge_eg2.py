"""Score the N1+EG2 run on the remaining EnterpriseRAG question types and merge it with the first 300 questions.

usage: merge_eg2.py <data root with enterprise/> <run.jsonl of the 170 remaining questions> <out: per-question scores for all 470>
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evalkit import load_questions, load_run, score_run

ROOT, RUN, OUT = sys.argv[1:4]
REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reference", "enterprise")
qs = load_questions("enterprise", ROOT)
run = load_run(RUN)
new = score_run(qs, run, list(run))
old = {r["qid"]: r for r in map(json.loads, open(os.path.join(REF, "taguri_n1_eg2.jsonl")))}
assert not set(new) & set(old), "the two runs overlap"
rows = {**old, **{q: {"qid": q, **s} for q, s in new.items()}}
with open(OUT, "w") as f:
    for q in sorted(rows):
        f.write(json.dumps(rows[q]) + "\n")
print(len(old), "+", len(new), "=", len(rows))
