"""End-to-end spot check on EnterpriseRAG-Bench: does better retrieval give better answers?

For each sampled question and each retrieval arm, Gemma 4 26B answers from the top-10 retrieved documents (one best
passage per document), then every reference fact and the overall correctness are graded with the jevlike read
(first-token Yes/No). Arms:
  N0      lexical layer only
  N1      Taguri
  N1+EG2  Taguri with EG2 (only where that run exists: basic and semantic questions)
  gold    the reference documents themselves (upper bound for the generator)

The grader is the same model that wrote the answers, not the benchmark's official grader, so the numbers are only
comparable between these arms.
"""
import gzip
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from taguri.decide import GEMMA4_TEMPLATE_NOTHINK_BOS, SYS_MARK, USR_MARK, SGLangBackend, Stats

GEN_SYS = "You answer questions about a company's internal knowledge base. Use only the provided documents."
GEN_USR = ("Documents:\n{docs}\n\nQuestion: {q}\n\nAnswer the question completely and concisely, using only the documents above. "
           "If the documents do not contain the answer, reply exactly: Not found in the documents.")
JUDGE_SYS = "You are a decision engine. Answer with exactly one letter."
P_FACT = ("[State]\nQuestion: {q}\n\nAnswer under review:\n{a}\n\nFact: {f}\n\n[Question] Does the answer under review state this fact?\nA. Yes\nB. No\n\n"
          "Answer with the letter of the correct option only.")
P_CORRECT = ("[State]\nQuestion: {q}\n\nReference answer:\n{g}\n\nAnswer under review:\n{a}\n\n[Question] Is the answer under review correct according to the reference answer?\n"
             "A. Yes\nB. No\n\nAnswer with the letter of the correct option only.")
CTX_TOKENS = 11000


def wrap(system, user):
    return GEMMA4_TEMPLATE_NOTHINK_BOS.replace(USR_MARK, user).replace(SYS_MARK, system)


def main(base_url, tokenizer_json, ix, qfile, runs, out_dir, log=print, commit=lambda: None):
    """runs: {"N1": dir, "N1+EG2": dir} (trace.jsonl.gz + run.jsonl); N0 and gold are computed here."""
    import requests

    os.makedirs(out_dir, exist_ok=True)
    backend = SGLangBackend(base_url, tokenizer_json, cache_dir=os.path.join(out_dir, "cache"), run_id="rag")
    tok = backend.tok
    qs = [json.loads(l) for l in open(qfile, encoding="utf-8")]
    traces = {}
    for arm, d in runs.items():
        tr = {}
        for l in gzip.open(os.path.join(d, "trace.jsonl.gz"), "rt"):
            r = json.loads(l); tr[r["qid"]] = r
        rn = {json.loads(l)["qid"]: json.loads(l)["retrieved"] for l in open(os.path.join(d, "run.jsonl"))}
        traces[arm] = (tr, rn)

    def passages_for(q, arm):
        """-> [(doc, passage dict)] top-10 documents, one passage each."""
        base = [ix.passage(r) for r, _ in ix.search(q["question"], 100)]
        best_bm25 = {}
        for p in base:
            best_bm25.setdefault(p["doc"], p)
        if arm == "N0":
            return list(best_bm25.items())[:10]
        if arm == "gold":
            out = []
            for d in q["gold_docs"][:10]:
                rows = ix.con.execute("SELECT rid FROM passages WHERE doc=? ORDER BY rid LIMIT 3", (d,)).fetchall()
                out += [(d, ix.passage(r[0])) for r in rows]
            return out
        tr, rn = traces[arm]
        if q["qid"] not in tr:
            return None
        best = {}
        for x in tr[q["qid"]]["judged"]:
            d = x["pid"].split("#")[0]
            if d not in best or x["lo"] > best[d][0]:
                best[d] = (x["lo"], x["pid"])
        out = []
        for d in rn[q["qid"]][:10]:
            if d in best:
                out.append((d, ix.passage(ix.rid_of(best[d][1]))))
            elif d in best_bm25:
                out.append((d, best_bm25[d]))
        return out

    def context(ps):
        parts, used = [], 0
        for i, (_, p) in enumerate(ps, 1):
            t = f"[{i}] {p['title']}\n{p['text']}"
            n = len(tok.encode(t, add_special_tokens=False).ids)
            if used + n > CTX_TOKENS and parts:
                break
            parts.append(t); used += n
        return "\n\n".join(parts), len(parts)

    tls = threading.local()

    def generate(prompt):
        if not hasattr(tls, "s"):
            tls.s = requests.Session()
        ids = tok.encode(prompt, add_special_tokens=False).ids
        body = {"input_ids": ids, "sampling_params": {"max_new_tokens": 400, "temperature": 0, "stop": ["<turn|>"]}}
        for attempt in range(4):
            try:
                r = tls.s.post(base_url + "/generate", json=body, timeout=900)
                r.raise_for_status()
                return r.json()["text"].replace("<turn|>", "").strip()
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(3)

    arms = ["N0", "N1"] + [a for a in runs if a != "N1"] + ["gold"]

    # Phase 1: generation only. Phase 2: grading only. (This SGLang build crashes when a plain generation request and a
    # token_ids_logprob request land in the same batch.)
    def gen_one(q):
        row = {"qid": q["qid"], "type": q["type"], "question": q["question"], "gold_answer": q["gold_answer"], "n_facts": len(q["facts"]), "arms": {}}
        for arm in arms:
            ps = passages_for(q, arm)
            if ps is None:
                continue
            ctx, n_used = context(ps)
            ans = generate(wrap(GEN_SYS, GEN_USR.format(docs=ctx, q=q["question"])))
            docs = list(dict.fromkeys(d for d, _ in ps))
            row["arms"][arm] = {"answer": ans, "docs": docs[:10], "passages_in_context": n_used,
                                "doc_recall": len(set(q["gold_docs"]) & set(docs[:10])) / len(q["gold_docs"]),
                                "not_found": ans.lower().startswith("not found")}
        return row

    def grade_one(args):
        q, row = args
        st = Stats()
        for arm, x in row["arms"].items():
            ans = x["answer"]
            fr = backend.ask([wrap(JUDGE_SYS, P_FACT.format(q=q["question"], a=ans, f=f)) for f in q["facts"]], 2, st) if q["facts"] else []
            cr = backend.ask([wrap(JUDGE_SYS, P_CORRECT.format(q=q["question"], g=q["gold_answer"], a=ans))], 2, st)[0]
            facts = [r["lp"][0] > r["lp"][1] for r in fr]
            x.update(facts=facts, completeness=(sum(facts) / len(facts)) if facts else None,
                     correct=cr["lp"][0] > cr["lp"][1], correct_lo=cr["lp"][0] - cr["lp"][1])
        return row

    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(gen_one, qs))
    log(f"  generation done ({time.time() - t0:.0f}s)")
    with ThreadPoolExecutor(8) as ex:
        rows = list(ex.map(grade_one, zip(qs, rows)))
    log(f"  grading done ({time.time() - t0:.0f}s)")
    with open(os.path.join(out_dir, "rag100.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    backend.flush(); commit()
    summ = {}
    for arm in arms:
        xs = [r["arms"][arm] for r in rows if arm in r["arms"]]
        cs = [x["completeness"] for x in xs if x["completeness"] is not None]
        summ[arm] = {"n": len(xs), "doc_recall": round(100 * sum(x["doc_recall"] for x in xs) / len(xs), 1), "correct": round(100 * sum(x["correct"] for x in xs) / len(xs), 1),
                     "completeness": round(100 * sum(cs) / len(cs), 1), "correct_x_complete": round(100 * sum((x["completeness"] or 0) * x["correct"] for x in xs) / len(xs), 1),
                     "not_found": sum(x["not_found"] for x in xs)}
    summ["wall_s"] = round(time.time() - t0, 1)
    json.dump(summ, open(os.path.join(out_dir, "summary.json"), "w"), indent=1)
    commit()
    return summ
