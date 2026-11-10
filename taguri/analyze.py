"""Normalisation and per-field tokenisation (handoff §7.1).

The *key* (what the index matches on) is NFKC + half-width + lower-case + diacritics folded + one Chinese
script (OpenCC). The key is only ever used for matching: every token carries the span of the ORIGINAL text it
came from, so callers can always show the original spelling.

Fields
  cjk_bigram  character bigrams of each CJK run (a lone character is kept as a unigram)
  cjk_word    jieba search-mode words of each CJK run
  latin       lower-cased, stop-words removed, Snowball(English) stems
  ids         alphanumeric codes kept whole (no splitting, no stemming)
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

_CJK_RANGES = "぀-ヿ㐀-䶿一-鿿豈-﫿가-힯"
CJK_RUN = re.compile(f"[{_CJK_RANGES}]+")
ID_RE = re.compile(r"[a-z0-9][a-z0-9\-_./]{2,}")
WORD_RE = re.compile(rf"[^\W\d_{_CJK_RANGES}]+", re.UNICODE)
HAS_DIGIT = re.compile(r"\d")
ALPHA_PART = re.compile(r"[a-z]{2,}")

# Our own short function-word list (articles, pronouns, prepositions, auxiliaries, wh-words, conjunctions).
STOP_EN = frozenset("""
a an the this that these those it its he she they them his her their we us our you your i me my
is are was were be been being am do does did done doing have has had having will would shall should can could may
might must of in on at by for with from to into onto over under about after before between during through as than
and or but nor so if then else not no yes also too very just only own same such both each few more most other some
any all which who whom whose what when where why how there here s t d ll re ve m
""".split())
STOP_ZH = frozenset("的 了 和 是 在 也 就 都 而 及 與 与 或 之 其 于 於 以 為 为 这 這 那 有 被 把 对 對 等 并 並 但 个 個 们 們".split())


@dataclass
class Token:
    key: str
    start: int  # span in the ORIGINAL text
    end: int


@dataclass
class Analysis:
    cjk_bigram: list = field(default_factory=list)
    cjk_word: list = field(default_factory=list)
    latin: list = field(default_factory=list)
    ids: list = field(default_factory=list)

    def keys(self, name):
        return [t.key for t in getattr(self, name)]

    def all_keys(self, fields=("cjk_bigram", "cjk_word", "latin", "ids")):
        out = []
        for f in fields:
            out.extend(self.keys(f))
        return out


class Analyzer:
    """zh_key: OpenCC config for the matching key ('t2s' | 'tw2sp' | 's2twp' | None = leave script as is)."""

    def __init__(self, zh_key="tw2sp", use_bigram=True, use_word=True, jieba_dict=None, user_words=()):
        self.zh_key = zh_key
        self.use_bigram, self.use_word = use_bigram, use_word
        self._cc = None
        self._jieba = None
        self._jieba_dict = jieba_dict
        self._user_words = tuple(user_words)
        self._stem_cache = {}
        import snowballstemmer

        self._stemmer = snowballstemmer.stemmer("english")

    # ------------------------------------------------------------------ normalisation
    def normalize(self, text):
        """-> (key string, offsets) where offsets[i] is the index in `text` that key[i] came from."""
        if text.isascii():
            return text.lower(), None  # identity mapping
        out, off = [], []
        for i, ch in enumerate(text):
            n = ch if ch.isascii() else unicodedata.normalize("NFKC", ch)
            n = n.lower()
            if not n.isascii() and not CJK_RUN.match(n[0]):
                n = "".join(c for c in unicodedata.normalize("NFKD", n) if not unicodedata.combining(c)) or n
            out.append(n)
            off.extend([i] * len(n))
        key = "".join(out)
        if self.zh_key and CJK_RUN.search(key):
            key, off = self._convert_cjk(key, off)
        return key, off

    def _convert_cjk(self, key, off):
        if self._cc is None:
            from opencc import OpenCC

            self._cc = OpenCC(self.zh_key)
        parts, new_off, pos = [], [], 0
        for m in CJK_RUN.finditer(key):
            parts.append(key[pos:m.start()]); new_off.extend(off[pos:m.start()])
            run = m.group()
            conv = self._cc.convert(run)
            run_off = off[m.start():m.end()]
            if len(conv) == len(run):
                new_off.extend(run_off)
            else:  # a phrase-level mapping changed the length: align with a diff, unmatched chars take the block start
                sm = difflib.SequenceMatcher(None, run, conv, autojunk=False)
                for tag, i1, i2, j1, j2 in sm.get_opcodes():
                    for j in range(j1, j2):
                        src = i1 + (j - j1) if (tag == "equal" or i1 + (j - j1) < i2) else max(i1, i2 - 1)
                        new_off.append(run_off[min(src, len(run_off) - 1)])
            parts.append(conv)
            pos = m.end()
        parts.append(key[pos:]); new_off.extend(off[pos:])
        return "".join(parts), new_off

    # ------------------------------------------------------------------ tokenisation
    def stem(self, w):
        s = self._stem_cache.get(w)
        if s is None:
            s = self._stem_cache[w] = self._stemmer.stemWord(w)
        return s

    def _jb(self):
        if self._jieba is None:
            import jieba
            import logging

            jieba.setLogLevel(logging.WARNING)
            tk = jieba.Tokenizer(dictionary=self._jieba_dict) if self._jieba_dict else jieba.Tokenizer()
            for w in self._user_words:
                tk.add_word(w)
            self._jieba = tk
        return self._jieba

    def analyze(self, text):
        key, off = self.normalize(text)
        n = len(text)

        def span(a, b):  # key span -> original span
            if off is None:
                return a, b
            return off[a], (off[b - 1] + 1 if b > a else off[a])

        res = Analysis()
        taken = []
        for m in ID_RE.finditer(key):
            tok = m.group().rstrip("-_./")
            if len(tok) < 3 or not HAS_DIGIT.search(tok):
                continue
            a, b = m.start(), m.start() + len(tok)
            res.ids.append(Token(tok, *span(a, b)))
            taken.append((a, b))
            if not tok.isdigit():  # alphabetic parts stay searchable on their own ("covid-19" -> "covid")
                for p in ALPHA_PART.finditer(tok):
                    w = p.group()
                    if w not in STOP_EN:
                        res.latin.append(Token(self.stem(w), *span(a + p.start(), a + p.end())))
        ti = 0
        for m in WORD_RE.finditer(key):
            a, b = m.start(), m.end()
            while ti < len(taken) and taken[ti][1] <= a:
                ti += 1
            if ti < len(taken) and taken[ti][0] <= a and b <= taken[ti][1]:
                continue
            w = m.group()
            if w in STOP_EN or (len(w) == 1 and w.isascii()):
                continue
            res.latin.append(Token(self.stem(w), *span(a, b)))
        res.latin.sort(key=lambda t: t.start)
        for m in CJK_RUN.finditer(key):
            run, a = m.group(), m.start()
            if self.use_bigram:
                if len(run) == 1:
                    res.cjk_bigram.append(Token(run, *span(a, a + 1)))
                for i in range(len(run) - 1):
                    res.cjk_bigram.append(Token(run[i:i + 2], *span(a + i, a + i + 2)))
            if self.use_word:
                for w, s, e in self._jb().tokenize(run, mode="search"):
                    if w in STOP_ZH:
                        continue
                    res.cjk_word.append(Token(w, *span(a + s, a + e)))
        return res

    def title_key(self, title):
        """Key used for exact title anchoring: every word (stop-words kept, unstemmed), codes and CJK characters
        of the normalised title, joined by single spaces."""
        return " ".join(k for k, _, _ in self.surface_tokens(title))

    def surface_tokens(self, text):
        """Unstemmed surface tokens with original spans: [(key, start, end)] in text order. CJK is one token per char."""
        key, off = self.normalize(text)
        out = []
        for m in re.finditer(rf"[{_CJK_RANGES}]|[^\W_{_CJK_RANGES}]+(?:[\-./][^\W_{_CJK_RANGES}]+)*", key):
            a, b = m.start(), m.end()
            if off is None:
                out.append((m.group(), a, b))
            else:
                out.append((m.group(), off[a], off[b - 1] + 1))
        return out
