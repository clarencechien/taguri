"""Judge calls (jevlike read: first-token log-probabilities of the option letters). §7.2 Q1, Q3, Q5, Q7.

Rules carried over from jevlike (handoff §3): template GEMMA4_TEMPLATE_NOTHINK_BOS unchanged, <bos> included,
thinking off, affirmative questions only, one passage per question, at most 4 options, candidates prepared by
the program, fixed option order. Raw log P of every option letter is returned and logged.

Prompt order is  template head -> question -> evidence so far -> candidate -> question text and options, so all
candidates of one round share a prefix (radix cache).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time

# jevlike decide/prompt.py: GEMMA4_TEMPLATE_NOTHINK_BOS (copied verbatim, not modified)
SYS_MARK, USR_MARK = "§SYSMARK§", "§USRMARK§"
GEMMA4_TEMPLATE_NOTHINK = ("<|turn>system\n" + SYS_MARK + "<turn|>\n<|turn>user\n" + USR_MARK + "<turn|>\n<|turn>model\n<|channel>thought\n<channel|>")
GEMMA4_TEMPLATE_NOTHINK_BOS = "<bos>" + GEMMA4_TEMPLATE_NOTHINK
LETTERS = "ABCD"

TEXT = {
    "en": {
        "system": "You are a decision engine. Answer with exactly one letter.",
        "state": "[State]\nQuestion: {q}\n\nEvidence found so far:\n{ev}\n",
        "none": "(none yet)",
        "ev_item": "- {title}: {text}",
        "cand": "\nCandidate passage:\n{title}: {text}\n",
        "q_evidence": "Does the candidate passage contain information needed for one of the steps in answering the question?",
        "q_pick": "To find the information that is still missing, which of these should be looked up next?",
        "q_enough": "Is the evidence found so far complete enough to answer the question?",
        "q_type": "Which kind of question is this?",
        "yes": "Yes", "no": "No",
        "types": ["Single-hop (one passage answers it directly)",
                  "Bridge (an intermediate entity has to be found first, then looked up)",
                  "Comparison (two or more named things are compared with each other)",
                  "Intersection (one thing has to satisfy several separate conditions)"],
        "question": "\n[Question] {instr}\n{opts}\n\nAnswer with the letter of the correct option only.",
    },
    "zh": {
        "system": "你是決策引擎。只回答一個字母。",
        "state": "【狀態】\n（問題）{q}\n\n（目前已有的證據）\n{ev}\n",
        "none": "（目前沒有）",
        "ev_item": "- （標題）{title}（內容）{text}",
        "cand": "\n（候選段落）\n（標題）{title}（內容）{text}\n",
        "q_evidence": "這個候選段落對回答問題有幫助嗎？（只要段落給出答案，或指出問題裡間接描述的人、地、作品或事物，就算有幫助）",
        "q_pick": "要找出還缺的資訊，接下來應該查哪一個？",
        "q_enough": "目前的證據足夠完整回答這個問題嗎？",
        "q_type": "這個問題屬於哪一種題型？",
        "yes": "是", "no": "否",
        "types": ["單跳（一段文字就能直接回答）",
                  "橋接（要先找出中間的實體，再去查它）",
                  "比較（把兩個以上有名稱的對象互相比較）",
                  "交集（同一個對象要同時符合幾個條件）"],
        "question": "\n【問題】{instr}\n{opts}\n\n只回答代表正確選項的字母。",
    },
}


def _clean(s):
    return " ".join((s or "").split())


# Wordings tried for the evidence question (Q3) on the calibration half; the chosen one is recorded in
# results/thresholds.lock.json ("q3_variant") and docs/design-decisions.md. Each entry: (instruction, yes label, no label).
Q3_VARIANTS = {
    "A": ("Does the candidate passage contain information needed for one of the steps in answering the question?", "Yes", "No"),
    "B": ("Does the candidate passage state a fact that helps answer the user question, either directly or as an intermediate step?", "Yes", "No"),
    "C": ("Is the candidate passage relevant evidence for the user question?",
          "Yes: it states a fact about something the user question refers to, and that fact helps reach the answer",
          "No: it gives nothing that helps reach the answer"),
    "D": ("Would a person answering the user question want to keep the candidate passage as a source?", "Yes", "No"),
    "G": ("Is the candidate passage about a person, place, work or thing that the user question or the evidence found so far names or describes?", "Yes", "No"),
    "I": ("Does the candidate passage help with the user question? A passage helps if it gives the answer, or if it identifies a person, place, work or "
          "thing that the user question describes indirectly.", "Yes", "No"),
    "E": ("Does the candidate passage tell us who, what, where or when something mentioned in the user question is, or give the answer itself?", "Yes", "No"),
}
# Chinese wordings of the evidence question, compared on the Chinese calibration set (results/s7d-zh-followup.md).
Q3_ZH = {
    "I": "這個候選段落對回答問題有幫助嗎？（只要段落給出答案，或指出問題裡間接描述的人、地、作品或事物，就算有幫助）",
    "B": "這個候選段落是否陳述了有助於回答問題的事實？（直接回答，或是回答過程中的某一步，都算）",
    "K": "這個候選段落和問題要找的答案有關嗎？（有關：段落給出答案，或說明問題裡提到的某個人、地、作品是誰、是什麼、在哪裡）",
}
STATE_L2 = "[State]\nUser question: {q}\n\nEvidence found so far:\n{ev}\n"


class Prompts:
    def __init__(self, lang="en", q3="A", layout="L1"):
        self.t = dict(TEXT["zh" if lang.startswith("zh") else "en"])
        if not lang.startswith("zh"):
            if layout == "L2":
                self.t["state"] = STATE_L2
            instr, yes, no = Q3_VARIANTS[q3]
            if layout == "L1":
                instr = instr.replace("the user question", "the question")
            self.t["q_evidence"], self.q3_opts = instr, [yes, no]
        else:
            self.t["q_evidence"] = Q3_ZH.get(q3, Q3_ZH["I"])
            self.q3_opts = [self.t["yes"], self.t["no"]]

    def _wrap(self, user):
        return GEMMA4_TEMPLATE_NOTHINK_BOS.replace(USR_MARK, user).replace(SYS_MARK, self.t["system"])

    def _state(self, q, evidence):
        ev = "\n".join(self.t["ev_item"].format(title=_clean(p["title"]), text=_clean(p["text"])) for p in evidence) or self.t["none"]
        return self.t["state"].format(q=_clean(q), ev=ev)

    def _question(self, instr, options):
        return self.t["question"].format(instr=instr, opts="\n".join(f"{LETTERS[i]}. {o}" for i, o in enumerate(options)))

    def evidence(self, q, evidence, cand):
        user = self._state(q, evidence) + self.t["cand"].format(title=_clean(cand["title"]), text=_clean(cand["text"])) + \
            self._question(self.t["q_evidence"], self.q3_opts)
        return self._wrap(user)

    def pick(self, q, evidence, terms):
        return self._wrap(self._state(q, evidence) + self._question(self.t["q_pick"], terms))

    def enough(self, q, evidence):
        return self._wrap(self._state(q, evidence) + self._question(self.t["q_enough"], [self.t["yes"], self.t["no"]]))

    def qtype(self, q):
        return self._wrap(self.t["state"].split("\n\n")[0].format(q=_clean(q)) + "\n" + self._question(self.t["q_type"], self.t["types"]))


class Stats:
    """Per-question accounting (handoff §3: judge calls, input tokens, time)."""

    def __init__(self):
        self.calls = 0          # logical judge calls
        self.fresh = 0          # calls that actually hit the server (not served from the cross-run result cache)
        self.tokens = 0         # input tokens of all logical calls
        self.fresh_tokens = 0
        self.radix_cached = 0   # of fresh_tokens, tokens the server reported as prefix-cache hits
        self.judge_s = 0.0      # wall time spent waiting for the server
        self.min_mass = 1.0

    def as_dict(self):
        return dict(self.__dict__)


class SGLangBackend:
    """Reads exact letter log-probs from SGLang /generate (input_ids, max_new_tokens=1)."""

    def __init__(self, base_url, tokenizer_json, cache_dir=None, run_id="run", batch=64):
        import requests
        from tokenizers import Tokenizer

        self.base_url, self.batch = base_url, batch
        self.tok = Tokenizer.from_file(tokenizer_json)
        self.letter_ids = []
        for L in LETTERS:
            ids = self.tok.encode(L, add_special_tokens=False).ids
            assert len(ids) == 1, f"letter {L} is not a single token: {ids}"
            self.letter_ids.append(ids[0])
        assert self.tok.encode("<bos>x", add_special_tokens=False).ids[0] == 2, "<bos> did not map to id 2"
        self._tls = threading.local()
        self._requests = requests
        self.cache, self._lock, self._fh = {}, threading.Lock(), None
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)
            for fn in sorted(os.listdir(cache_dir)):
                if fn.endswith(".jsonl"):
                    with open(os.path.join(cache_dir, fn)) as f:
                        for line in f:
                            try:
                                r = json.loads(line)
                                self.cache[r["k"]] = r
                            except Exception:  # noqa: BLE001  (a torn last line after a crash)
                                pass
            self._fh = open(os.path.join(cache_dir, f"{run_id}-{int(time.time())}.jsonl"), "a")
        self.loaded = len(self.cache)
        self.debug_dir, self._debug_n = None, 0

    def _sess(self):
        if not hasattr(self._tls, "s"):
            self._tls.s = self._requests.Session()
        return self._tls.s

    def ask(self, prompts, n_opts, stats: Stats, warm_first=False):
        """prompts: list[str] -> list of {"lp": [log P per option letter], "ntok", "mass"}."""
        import math

        keys = [hashlib.sha1((p + f"|{n_opts}").encode()).hexdigest() for p in prompts]
        out = [None] * len(prompts)
        todo = []
        for i, k in enumerate(keys):
            r = self.cache.get(k)
            if r is not None:
                out[i] = r
            else:
                todo.append(i)
        if todo:
            ids = {i: self.tok.encode(prompts[i], add_special_tokens=False).ids for i in todo}
            groups = []
            rest = todo
            if warm_first and len(todo) > 1:
                groups.append(todo[:1]); rest = todo[1:]
            groups += [rest[i:i + self.batch] for i in range(0, len(rest), self.batch)]
            want = self.letter_ids[:n_opts]
            for g in groups:
                body = {"input_ids": [ids[i] for i in g], "sampling_params": {"max_new_tokens": 1, "temperature": 0},
                        "return_logprob": True, "logprob_start_len": -1, "top_logprobs_num": 0, "token_ids_logprob": [want] * len(g)}
                t0 = time.perf_counter()
                for attempt in range(4):
                    try:
                        resp = self._sess().post(f"{self.base_url}/generate", json=body, timeout=900)
                        resp.raise_for_status()
                        break
                    except Exception:  # noqa: BLE001
                        if attempt == 3:
                            raise
                        time.sleep(2 * (attempt + 1))
                stats.judge_s += time.perf_counter() - t0
                rs = resp.json()
                rs = rs if isinstance(rs, list) else [rs]
                for i, r in zip(g, rs):
                    meta = r["meta_info"]
                    by_id = {int(it[1]): float(it[0]) for it in meta["output_token_ids_logprobs"][0]}
                    lp = [by_id[t] for t in want]
                    rec = {"k": keys[i], "lp": lp, "ntok": len(ids[i]), "mass": sum(math.exp(v) for v in lp)}
                    out[i] = rec
                    stats.fresh += 1
                    stats.fresh_tokens += len(ids[i])
                    stats.radix_cached += int(meta.get("cached_tokens") or 0)
                    with self._lock:
                        self.cache[keys[i]] = rec
                        if self._fh:
                            self._fh.write(json.dumps(rec) + "\n")
        if self.debug_dir and n_opts > 2:  # diagnostic: what does the model want to say when the option letters get little mass?
            for i, r in enumerate(out):
                if r["mass"] < 0.5 and self._debug_n < 60:
                    self._debug_n += 1
                    body = {"input_ids": self.tok.encode(prompts[i], add_special_tokens=False).ids, "sampling_params": {"max_new_tokens": 1, "temperature": 0},
                            "return_logprob": True, "logprob_start_len": -1, "top_logprobs_num": 8, "return_text_in_logprobs": True,
                            "token_ids_logprob": self.letter_ids}
                    m = self._sess().post(f"{self.base_url}/generate", json=body, timeout=300).json()
                    top = [[round(t[0], 2), t[2]] for t in m["meta_info"]["output_top_logprobs"][0]]
                    with self._lock, open(os.path.join(self.debug_dir, "lowmass.jsonl"), "a") as f:
                        f.write(json.dumps({"mass": r["mass"], "lp": r["lp"], "top": top, "text": m.get("text"), "prompt_tail": prompts[i][-700:]}, ensure_ascii=False) + "\n")
        for r in out:
            stats.calls += 1
            stats.tokens += r["ntok"]
            stats.min_mass = min(stats.min_mass, r["mass"])
        return out

    def flush(self):
        with self._lock:
            if self._fh:
                self._fh.flush()
                os.fsync(self._fh.fileno())


class LLMDecider:
    def __init__(self, backend, lang="en", q3="A", layout="L1"):
        self.b, self.p = backend, Prompts(lang, q3, layout)
        self._ntok = {}

    EV_TOKEN_BUDGET = 10000  # context is 16,384; leaves room for the longest candidate passage and the question

    def _fit(self, evidence):
        """Keep the best-ranked evidence passages that fit the token budget (long enterprise chunks can overflow the context)."""
        tok = getattr(self.b, "tok", None)
        if tok is None or not evidence:
            return evidence
        out, used = [], 0
        for p in evidence:
            n = self._ntok.get(p["rid"])
            if n is None:
                n = self._ntok[p["rid"]] = len(tok.encode(p["title"] + ": " + p["text"], add_special_tokens=False).ids) + 4
            if used + n > self.EV_TOKEN_BUDGET and out:
                break
            out.append(p); used += n
        return out

    def evidence(self, q, evidence, cands, stats):
        """-> [{"lpA", "lpB", "lo"}] aligned with cands."""
        evidence = self._fit(evidence)
        prompts = [self.p.evidence(q["question"], evidence, c) for c in cands]
        rs = self.b.ask(prompts, 2, stats, warm_first=bool(evidence))
        return [{"lpA": r["lp"][0], "lpB": r["lp"][1], "lo": r["lp"][0] - r["lp"][1], "mass": r["mass"]} for r in rs]

    def pick(self, q, evidence, terms, stats):
        """terms: 2..4 strings -> list of log P per option."""
        return self.b.ask([self.p.pick(q["question"], self._fit(evidence), terms)], len(terms), stats)[0]["lp"]

    def none_label(self):
        return "以上都不適合" if self.p.t["yes"] == "是" else "None of these"

    def enough(self, q, evidence, stats):
        lp = self.b.ask([self.p.enough(q["question"], self._fit(evidence))], 2, stats)[0]["lp"]
        return {"lpA": lp[0], "lpB": lp[1], "lo": lp[0] - lp[1]}

    def qtype(self, q, stats):
        return self.b.ask([self.p.qtype(q["question"])], 4, stats)[0]["lp"]


class OracleDecider:
    """CPU-only stand-in used to debug the pipeline and to bound what the program side can reach:
    evidence = gold membership; pick = the candidate whose lookup reaches the most missing gold (set by the
    pipeline through `pick_hook`); enough = every gold passage is in the pool."""

    def __init__(self, gold_rids_of, pick_hook=None, noise=None):
        self.gold_rids_of, self.pick_hook = gold_rids_of, pick_hook

    def evidence(self, q, evidence, cands, stats):
        g = self.gold_rids_of(q)
        stats.calls += len(cands)
        return [{"lpA": 0.0, "lpB": 0.0, "lo": 8.0 if c["rid"] in g else -8.0, "mass": 1.0} for c in cands]

    def pick(self, q, evidence, terms, stats):
        stats.calls += 1
        sc = self.pick_hook(q, evidence, terms) if self.pick_hook else [0.0] * len(terms)
        return [s - i * 1e-6 for i, s in enumerate(sc)]

    def none_label(self):
        return "None of these"

    def enough(self, q, evidence, stats):
        stats.calls += 1
        g = self.gold_rids_of(q)
        ok = g <= {p["rid"] for p in evidence}
        return {"lpA": 0.0, "lpB": 0.0, "lo": 5.0 if ok else -5.0}

    def qtype(self, q, stats):
        stats.calls += 1
        return [0.0, 1.0, 0.0, 0.0]
