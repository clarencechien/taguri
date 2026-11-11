"""SQLite FTS5 index with per-field pre-tokenised columns, BM25F-style column weights and a title lookup (§7.1)."""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time

from .analyze import STOP_EN, Analyzer

FIELDS = ("title", "cjk_bigram", "cjk_word", "latin", "ids")
DEFAULT_WEIGHTS = {"title": 2.0, "cjk_bigram": 1.0, "cjk_word": 1.0, "latin": 1.0, "ids": 1.0}
PAREN = re.compile(r"\s*[\(（][^\)）]*[\)）]\s*$")


def _q(tok):
    return '"' + tok.replace('"', '""') + '"'


_W = {}


def _init_worker(zh_key, use_bigram, use_word, jieba_dict, doc_field, analyzer=None):
    _W["an"] = analyzer or Analyzer(zh_key=zh_key, use_bigram=use_bigram, use_word=use_word, jieba_dict=jieba_dict)
    _W["doc_field"] = doc_field


def _analyze_line(line):
    an, doc_field = _W["an"], _W["doc_field"]
    r = json.loads(line)
    title, text = r.get("title") or "", r.get("text") or ""
    ta, xa = an.analyze(title), an.analyze(text)
    fts = (" ".join(ta.all_keys()), " ".join(xa.keys("cjk_bigram")), " ".join(xa.keys("cjk_word")), " ".join(xa.keys("latin")), " ".join(xa.keys("ids")))
    pas = (str(r["pid"]), str(r.get(doc_field) or r["pid"]) if doc_field else str(r["pid"]), title, text)
    keys = {k for k in (an.title_key(title), an.title_key(PAREN.sub("", title))) if k}
    return fts, pas, keys


def build(corpus_path, db_path, analyzer: Analyzer, doc_field=None, log=print, workers=1):
    """corpus.jsonl rows: {"pid", "title", "text"[, doc_field]}."""
    if os.path.exists(db_path):
        os.remove(db_path)
    t0 = time.time()
    con = sqlite3.connect(db_path)
    con.executescript(
        "PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;"
        "CREATE VIRTUAL TABLE fts USING fts5(title, cjk_bigram, cjk_word, latin, ids, "
        "tokenize=\"unicode61 remove_diacritics 0 tokenchars '-_./'\");"
        "CREATE TABLE passages(rid INTEGER PRIMARY KEY, pid TEXT UNIQUE, doc TEXT, title TEXT, text TEXT);"
        "CREATE TABLE title_lookup(key TEXT, rid INTEGER);"
        "CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);"
    )
    rows, n = [], 0

    def lines():
        with open(corpus_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield line

    if workers > 1:
        import multiprocessing as mp

        pool = mp.Pool(workers, initializer=_init_worker, initargs=(analyzer.zh_key, analyzer.use_bigram, analyzer.use_word, analyzer._jieba_dict, doc_field))
        it = pool.imap(_analyze_line, lines(), chunksize=200)
    else:
        _init_worker(None, None, None, None, doc_field, analyzer)
        it = map(_analyze_line, lines())
    for fts_row, pas_row, keys in it:
        n += 1
        con.execute("INSERT INTO fts(rowid, title, cjk_bigram, cjk_word, latin, ids) VALUES (?,?,?,?,?,?)", (n, *fts_row))
        con.execute("INSERT INTO passages VALUES (?,?,?,?,?)", (n, *pas_row))
        rows.extend((k, n) for k in keys)
        if n % 50000 == 0:
            log(f"  indexed {n} passages ({time.time() - t0:.0f}s)")
            con.commit()
    if workers > 1:
        pool.close(); pool.join()
    con.executemany("INSERT INTO title_lookup VALUES (?,?)", rows)
    con.execute("CREATE INDEX title_lookup_key ON title_lookup(key)")
    con.execute("CREATE INDEX passages_doc ON passages(doc)")
    con.execute("INSERT INTO meta VALUES ('n', ?)", (str(n),))
    con.execute("INSERT INTO meta VALUES ('zh_key', ?)", (str(analyzer.zh_key),))
    con.execute("INSERT INTO meta VALUES ('fields', ?)", (json.dumps({"bigram": analyzer.use_bigram, "word": analyzer.use_word}),))
    con.execute("INSERT INTO fts(fts) VALUES ('optimize')")
    con.commit()
    con.close()
    return {"passages": n, "build_s": round(time.time() - t0, 1), "db_bytes": os.path.getsize(db_path)}


class Index:
    LOOKUP_MAX = 4      # restricted searches over more rowids than this use one filtered pass
    FULL_DEPTH = 200    # unrestricted searches are computed to at least this depth, then cached
    CACHE_QUERIES = 16  # result lists kept per thread

    def __init__(self, db_path, analyzer: Analyzer, weights=None):
        self.db_path, self.an = db_path, analyzer
        self.weights = dict(DEFAULT_WEIGHTS, **(weights or {}))
        self._tls = threading.local()
        self.n = int(self.con.execute("SELECT v FROM meta WHERE k='n'").fetchone()[0])
        self._df_cache = {}

    @property
    def con(self):
        c = getattr(self._tls, "con", None)
        if c is None:
            c = self._tls.con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
        return c

    def _bm25(self):
        return "bm25(fts, %s)" % ", ".join(str(float(self.weights[f])) for f in FIELDS)

    # ------------------------------------------------------------------ lookups
    def passage(self, rid):
        r = self.con.execute("SELECT pid, doc, title, text FROM passages WHERE rid=?", (rid,)).fetchone()
        return {"rid": rid, "pid": r[0], "doc": r[1], "title": r[2], "text": r[3]}

    def rid_of(self, pid):
        r = self.con.execute("SELECT rid FROM passages WHERE pid=?", (str(pid),)).fetchone()
        return r[0] if r else None

    # ------------------------------------------------------------------ search
    def query_keys(self, text):
        return list(dict.fromkeys(self.an.analyze(text).all_keys()))

    def search_keys(self, keys, k=50, restrict=None):
        """-> [(rid, score)] best first; score is positive (higher is better)."""
        keys = [x for x in dict.fromkeys(keys) if x]
        if not keys:
            return []
        match = " OR ".join(_q(x) for x in keys)
        if restrict is not None:
            restrict = list(dict.fromkeys(restrict))
            # A plain "rowid IN (...)" makes SQLite run the MATCH once per rowid, and FTS5 recomputes the document
            # frequency of every query term each time (0.1 s per rowid on 1.5M passages). "+rowid" turns it into one
            # pass over the matches that only scores the rows asked for. Same rows, same scores.
            col = "rowid" if len(restrict) <= self.LOOKUP_MAX else "+rowid"
            out = []
            for i in range(0, len(restrict), 900):
                part = restrict[i:i + 900]
                out += self.con.execute(f"SELECT rowid, -{self._bm25()} FROM fts WHERE fts MATCH ? AND {col} IN ({','.join('?' * len(part))})",
                                        (match, *part)).fetchall()
            return sorted(out, key=lambda x: (-x[1], x[0]))
        # The same query comes back several times within one question (first pass, every expansion round), each
        # time scoring every matching passage. Keep the last few result lists per thread; a shorter list is a
        # prefix of a longer one because the order is total (score, then rowid).
        cache = getattr(self._tls, "full", None)
        if cache is None:
            cache = self._tls.full = {}
        hit = cache.get(match)
        if hit is None or hit[0] < k:
            depth = max(k, self.FULL_DEPTH)
            rows = self.con.execute(f"SELECT rowid, -{self._bm25()} AS s FROM fts WHERE fts MATCH ? ORDER BY s DESC, rowid LIMIT ?",
                                    (match, depth)).fetchall()
            if len(cache) >= self.CACHE_QUERIES:
                cache.pop(next(iter(cache)))
            hit = cache[match] = (depth, rows)
        return hit[1][:k]

    def search(self, text, k=50):
        return self.search_keys(self.query_keys(text), k)

    def fused_search(self, base_keys, term_keys, k=50, beta=2.0, depth=200):
        """score = bm25(base) + beta * bm25(terms); candidates are the union of both top-`depth` lists."""
        a = dict(self.search_keys(base_keys, depth))
        b = dict(self.search_keys(term_keys, depth))
        miss_a = [r for r in b if r not in a]
        miss_b = [r for r in a if r not in b]
        if miss_a:
            a.update(dict(self.search_keys(base_keys, restrict=miss_a)))
        if miss_b and term_keys:
            b.update(dict(self.search_keys(term_keys, restrict=miss_b)))
        sc = {r: a.get(r, 0.0) + beta * b.get(r, 0.0) for r in set(a) | set(b)}
        return sorted(sc.items(), key=lambda x: (-x[1], x[0]))[:k]

    # ------------------------------------------------------------------ anchoring (Q0)
    def anchors(self, text, max_words=8, max_cjk=15, per_key=5, id_df_cap=50):
        """Exact matches between n-grams of the query and title_lookup keys / ids-field codes.
        -> [{"key", "span": (start, end) in the original text, "rids": [...], "kind": "title"|"id"}], maximal matches only."""
        toks = self.an.surface_tokens(text)
        hits = []
        for i in range(len(toks)):
            cjk = len(toks[i][0]) == 1 and not toks[i][0].isascii()
            for n in range(min(max_cjk if cjk else max_words, len(toks) - i), 0, -1):
                gram = toks[i:i + n]
                if n == 1 and (gram[0][0] in STOP_EN or len(gram[0][0]) < 2 or gram[0][0].isdigit()):
                    continue
                key = " ".join(g[0] for g in gram)
                rids = [r[0] for r in self.con.execute("SELECT rid FROM title_lookup WHERE key=? LIMIT 200", (key,))]
                if rids:
                    hits.append({"key": key, "span": (gram[0][1], gram[-1][2]), "rids": rids, "kind": "title", "i": i, "n": n})
                    break  # longest match starting at i
        keep = []
        for h in hits:  # drop matches nested inside a longer one
            if not any(o is not h and o["i"] <= h["i"] and h["i"] + h["n"] <= o["i"] + o["n"] and o["n"] > h["n"] for o in hits):
                keep.append(h)
        for t in self.an.analyze(text).ids:
            if t.key.isdigit() and len(t.key) <= 4:
                continue  # years and small numbers are not identifiers
            rids = [r[0] for r in self.con.execute("SELECT rowid FROM fts WHERE fts MATCH ? LIMIT ?", ("ids : " + _q(t.key), id_df_cap + 1))]
            if 0 < len(rids) <= id_df_cap:
                keep.append({"key": t.key, "span": (t.start, t.end), "rids": rids, "kind": "id"})
        for h in keep:
            h.pop("i", None); h.pop("n", None)
            h["text"] = text[h["span"][0]:h["span"][1]]
        return keep

    # ------------------------------------------------------------------ statistics
    def phrase_rids(self, keys, limit=300):
        """Passages containing the key sequence as a phrase in any field."""
        keys = [x for x in keys if x]
        if not keys:
            return []
        phrase = '"' + " ".join(k.replace('"', '""') for k in keys) + '"'
        return [r[0] for r in self.con.execute("SELECT rowid FROM fts WHERE fts MATCH ? LIMIT ?", (phrase, limit))]

    def phrase_df(self, keys):
        keys = tuple(x for x in keys if x)
        if not keys:
            return 0
        v = self._df_cache.get(keys)
        if v is None:
            phrase = '"' + " ".join(k.replace('"', '""') for k in keys) + '"'
            v = self.con.execute("SELECT count(*) FROM fts WHERE fts MATCH ?", (phrase,)).fetchone()[0]
            if len(self._df_cache) < 500000:
                self._df_cache[keys] = v
        return v

    def idf(self, df):
        return math.log(1.0 + (self.n - df + 0.5) / (df + 0.5))
