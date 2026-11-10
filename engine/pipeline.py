"""Query pipeline Q0..Q8 (handoff §7.2)."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from .analyze import STOP_EN, CJK_RUN
from .decide import Stats


@dataclass
class Config:
    name: str = "N0"
    judge: bool = False          # Q3/Q4/Q8 (N1+)
    bridge: str = "judge"        # Q5: "judge" (N1) | "idf" (N1c)
    rounds: int = 2              # expansion rounds (N1: fixed 2)
    adaptive: bool = False       # Q7 (N2): stop when the judge says the evidence is enough; rounds = max
    route: bool = False          # Q1 (N3)
    dense: bool = False          # Q2b (N4)
    K: int = 50
    m: int = 8
    tau: float = 0.0
    n_terms: int = 2
    n_cand: int = 8
    beta: float = 2.0            # weight of the selected terms in the next-round query
    dense_k: int = 20
    anchor_bonus: float = 0.0    # N0 only: score bonus for exact title/id anchors
    out_mode: str = "pool_then_bm25"   # Q8: "pool_then_bm25" | "all_logodds"
    out_k: int = 10


CONFIGS = {
    "N0": dict(judge=False),
    "N1": dict(judge=True, bridge="judge", rounds=2),
    "N1c": dict(judge=True, bridge="idf", rounds=2),
    "N2": dict(judge=True, adaptive=True, rounds=3),
    "N3": dict(judge=True, adaptive=True, rounds=3, route=True),
}

CONNECT = frozenset("of the de la del van von der di da du le and for in on at al el bin ibn y e".split())
CAP_TOKEN = re.compile(r"[^\W_]+(?:['’.\-][^\W_]+)*\.?|[^\s]", re.UNICODE)


def cap_phrases(text):
    """Runs of capitalised words in the original text (connectors allowed inside). -> [(phrase, start, end)]"""
    out, run = [], []

    def flush():
        while run and run[-1][0].lower().rstrip(".") in CONNECT:
            run.pop()
        while run and run[0][0].lower() in STOP_EN:  # sentence-initial "The", "In", ...
            run.pop(0)
        if run:
            s, e = run[0][1], run[-1][2]
            out.append((text[s:e].rstrip("."), s, e))
        run.clear()

    for m in CAP_TOKEN.finditer(text):
        w = m.group()
        if len(w) == 1 and not w.isalnum():
            flush()
            continue
        capital = w[0].isupper() and not CJK_RUN.match(w[0])
        if capital:
            run.append((w, m.start(), m.end()))
            if w.endswith(".") and len(w) > 4:  # a sentence end, not an abbreviation
                flush()
        elif run and w.lower() in CONNECT:
            run.append((w, m.start(), m.end()))
        else:
            flush()
    flush()
    return out


class Term:
    __slots__ = ("text", "keys", "phrases", "df", "idf", "src", "anchorable")

    def __init__(self, text, keys, phrases, src):
        self.text, self.keys, self.phrases, self.src = text, keys, phrases, src
        self.df = self.idf = None
        self.anchorable = False


class Engine:
    def __init__(self, index, decider=None, dense=None, doc_level=False):
        self.ix, self.dec, self.dense, self.doc_level = index, decider, dense, doc_level

    # ------------------------------------------------------------------ helpers
    def _term(self, text, src):
        a = self.ix.an.analyze(text)
        lat = a.keys("latin") + a.keys("ids")
        cjk = a.keys("cjk_bigram") or a.keys("cjk_word")
        keys = list(dict.fromkeys(a.all_keys()))
        if not keys:
            return None
        phrases = []
        if a.latin:
            phrases.append(a.keys("latin"))
        for t in a.ids:
            phrases.append([t.key])
        if cjk:
            phrases.append(cjk)
        return Term(" ".join(text.split()), keys, phrases, src)

    def _term_rids(self, term, limit=300):
        sets = [set(self.ix.phrase_rids(p, limit)) for p in term.phrases]
        return set.intersection(*sets) if sets else set()

    def bridge_candidates(self, pool, seen_keys, judged, cfg, used):
        """Program-side candidate preparation for Q5: titles, codes, capitalised runs and high-IDF Chinese words of
        the evidence pool, minus anything already in a query; ranked by IDF; top n_cand."""
        terms, seen_text = [], set(used)
        for p in pool:
            raw = [(p["title"], "title")]
            body = p["text"]
            a = self.ix.an.analyze(body)
            raw += [(body[t.start:t.end], "id") for t in a.ids if not (t.key.isdigit() and len(t.key) < 4)]
            raw += [(ph, "cap") for ph, _, _ in cap_phrases(body)]
            if a.cjk_word:
                ws = {}
                for t in a.cjk_word:
                    if len(t.key) >= 2:
                        ws.setdefault(t.key, body[t.start:t.end])
                scored = sorted(ws.items(), key=lambda kv: (self.ix.phrase_df([kv[0]]), kv[0]))
                raw += [(orig, "zh") for _, orig in scored[:12]]
            for text, src in raw:
                text = text.strip()
                norm = " ".join(text.lower().split())
                if not text or norm in seen_text or len(text) > 80:
                    continue
                seen_text.add(norm)
                t = self._term(text, src)
                if t is None or set(t.keys) <= seen_keys:
                    continue
                rids = self._term_rids(t)
                if not any(r not in judged for r in rids):
                    continue  # looking it up cannot surface anything new
                t.df = self.ix.phrase_df(t.phrases[0]) if len(t.phrases) == 1 else len(rids)
                t.df = max(t.df, 1)
                t.idf = self.ix.idf(t.df)
                terms.append(t)
        terms.sort(key=lambda t: (-t.idf, t.text))
        return terms[:cfg.n_cand]

    def choose_terms(self, q, pool, cands, cfg, stats, trace):
        """Q5. N1c: the n_terms highest-IDF candidates. N1: knockout in groups of <= 4, judge picks one per group."""
        if len(cands) <= cfg.n_terms:
            trace["picks"].append({"cands": [t.text for t in cands], "mode": "all"})
            return cands
        if cfg.bridge == "idf":
            trace["picks"].append({"cands": [t.text for t in cands], "mode": "idf", "chosen": [t.text for t in cands[:cfg.n_terms]]})
            return cands[:cfg.n_terms]
        if len(cands) <= 4:
            lp = self.dec.pick(q, pool, [t.text for t in cands], stats)
            order = sorted(range(len(cands)), key=lambda i: (-lp[i], i))
            chosen = [cands[i] for i in order[:cfg.n_terms]]
            trace["picks"].append({"groups": [[t.text for t in cands]], "lp": [lp], "chosen": [t.text for t in chosen]})
            return chosen
        # snake deal by IDF rank so both groups get strong and weak candidates: ranks 1,4,5,8 | 2,3,6,7
        g1 = [c for i, c in enumerate(cands) if i % 4 in (0, 3)]
        g2 = [c for i, c in enumerate(cands) if i % 4 in (1, 2)]
        chosen, groups, lps = [], [], []
        for g in (g1, g2):
            if len(g) == 1:
                chosen.append(g[0]); groups.append([g[0].text]); lps.append([0.0])
                continue
            lp = self.dec.pick(q, pool, [t.text for t in g], stats)
            chosen.append(g[max(range(len(g)), key=lambda i: (lp[i], -i))])
            groups.append([t.text for t in g]); lps.append(lp)
        trace["picks"].append({"groups": groups, "lp": lps, "chosen": [t.text for t in chosen]})
        return chosen

    def _src(self, rid, cache):
        p = cache.get(rid)
        if p is None:
            p = cache[rid] = self.ix.passage(rid)
        return p

    # ------------------------------------------------------------------ one retrieval thread (Q2..Q7)
    def _thread(self, q, query_text, cfg, state, stats, trace, max_rounds):
        ix = self.ix
        judged, pcache = state["judged"], state["pcache"]
        base_keys = ix.query_keys(query_text)
        seen_keys = set(base_keys) | state["seen_keys"]
        cands = ix.search_keys(base_keys, cfg.K)
        for r, s in cands:
            state["bm25"].setdefault(r, s)
        rids = [r for r, _ in cands]
        for a in state["anchors"]:
            sc = ix.search_keys(base_keys, restrict=a["rids"]) if len(a["rids"]) > 5 else [(r, 0) for r in a["rids"]]
            rids += [r for r, _ in sc[:5]]
        dense_q = query_text
        used = set()
        for rnd in range(max_rounds + 1):
            if cfg.dense and self.dense is not None:
                have = set(rids)
                extra = [r for r in self.dense.search(dense_q, cfg.dense_k) if r not in have][:cfg.dense_k]
                state["dense_only"].update(r for r in extra if r not in judged)
                rids += extra
            new = [r for r in dict.fromkeys(rids) if r not in judged]
            pool = self._pool(state, cfg)
            if new:
                res = self.dec.evidence(q, pool, [self._src(r, pcache) for r in new], stats)
                for r, x in zip(new, res):
                    judged[r] = {"pid": pcache[r]["pid"], "lo": x["lo"], "lpA": x["lpA"], "lpB": x["lpB"], "round": state["round_base"] + rnd, "ctx": len(pool)}
            pool = self._pool(state, cfg)
            trace["rounds"].append({"round": state["round_base"] + rnd, "query": dense_q, "new": len(new), "pool": [p["pid"] for p in pool]})
            if rnd == max_rounds:
                break
            if cfg.adaptive and pool:
                e = self.dec.enough(q, pool, stats)
                trace["enough"].append({"round": state["round_base"] + rnd, **e})
                if e["lo"] > 0:
                    break
            src_pool = pool or [self._src(r, pcache) for r in sorted(judged, key=lambda r: (-judged[r]["lo"], r))[:2]]
            cand_terms = self.bridge_candidates(src_pool, seen_keys, judged, cfg, used)
            if not cand_terms:
                break
            chosen = self.choose_terms(q, pool, cand_terms, cfg, stats, trace)
            term_keys = []
            for t in chosen:
                term_keys += t.keys
                used.add(" ".join(t.text.lower().split()))
            seen_keys |= set(term_keys)
            nxt = ix.fused_search(base_keys, term_keys, cfg.K, cfg.beta)
            rids = [r for r, _ in nxt]
            dense_q = query_text + " " + " ".join(t.text for t in chosen)
        state["seen_keys"] = seen_keys
        return rnd

    def _pool(self, state, cfg):
        j = state["judged"]
        top = sorted((r for r in j if j[r]["lo"] >= cfg.tau), key=lambda r: (-j[r]["lo"], -state["bm25"].get(r, 0.0), r))[:cfg.m]
        return [self._src(r, state["pcache"]) for r in top]

    # ------------------------------------------------------------------ whole question
    def run(self, q, cfg: Config):
        """q: {"qid", "question"} -> {"qid", "retrieved": [...], "trace": {...}}"""
        ix = self.ix
        t0 = time.perf_counter()
        stats = Stats()
        text = q["question"]
        trace = {"rounds": [], "picks": [], "enough": [], "anchors": []}
        anchors = ix.anchors(text)
        trace["anchors"] = [{"text": a["text"], "kind": a["kind"], "n": len(a["rids"])} for a in anchors]
        base_keys = ix.query_keys(text)
        base = ix.search_keys(base_keys, max(cfg.K, 100))
        bm25 = dict(base)
        if not cfg.judge:
            sc = dict(base)
            if cfg.anchor_bonus:
                for a in anchors:
                    hit = ix.search_keys(base_keys, restrict=a["rids"]) if a["rids"] else []
                    for r, s in hit[:5]:
                        sc[r] = s + cfg.anchor_bonus
            order = sorted(sc, key=lambda r: (-sc[r], r))
            return self._finish(q, order, cfg, stats, trace, t0, {})
        state = {"judged": {}, "pcache": {}, "bm25": bm25, "anchors": anchors, "seen_keys": set(), "round_base": 0, "dense_only": set()}
        route = None
        if cfg.route:
            lp = self.dec.qtype(q, stats)
            route = max(range(4), key=lambda i: (lp[i], -i))
            trace["qtype"] = {"lp": lp, "route": route}
        if cfg.route and route in (2, 3) and len(anchors) >= 2:
            # comparison / intersection: one retrieval thread per anchored entity, all feeding one evidence pool
            for a in anchors[:4]:
                self._thread(q, text + " " + a["text"], cfg, state, stats, trace, cfg.rounds if not cfg.adaptive else 1)
                state["round_base"] += 10
        else:
            self._thread(q, text, cfg, state, stats, trace, cfg.rounds)
        j = state["judged"]
        if cfg.out_mode == "all_logodds":
            order = sorted(j, key=lambda r: (-j[r]["lo"], -bm25.get(r, 0.0), r))
        else:
            order = sorted((r for r in j if j[r]["lo"] >= cfg.tau), key=lambda r: (-j[r]["lo"], -bm25.get(r, 0.0), r))
        have = set(order)
        order += [r for r, _ in base if r not in have]  # fill with BM25F (original query)
        trace["dense_only"] = sorted(state["dense_only"])
        return self._finish(q, order, cfg, stats, trace, t0, j)

    def _finish(self, q, order, cfg, stats, trace, t0, judged):
        out, seen = [], set()
        for r in order:
            p = self.ix.passage(r)
            key = p["doc"] if self.doc_level else p["pid"]
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
            if len(out) >= max(cfg.out_k, 10):
                break
        trace["judged"] = list(judged.values())
        trace["stats"] = stats.as_dict()
        trace["wall_s"] = round(time.perf_counter() - t0, 3)
        return {"qid": q["qid"], "retrieved": out, "trace": trace}
