"""S7b: build dev-zh. Translates MuSiQue (all passages, all distinct titles, the 100 dev_zh_source questions) into
Traditional Chinese with Gemma 4 26B on a GENERATION SGLang server (separate from the judge runs), then derives
the Simplified copy with OpenCC tw2sp. Gold passage ids are unchanged. Runs inside modal_taguri.py::translate.

Step 1  every distinct title -> zh-TW, one table (title_map.json), so an entity is spelled the same everywhere.
Step 2  every passage, with the table entries for the titles that occur in it, asked to follow the table.
Step 3  the questions, same way.
"""
import json
import os
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

TEMPLATE = "<bos><|turn>system\n{sys}<turn|>\n<|turn>user\n{usr}<turn|>\n<|turn>model\n<|channel>thought\n<channel|>"
SYS = "你是專業的英翻中譯者，使用台灣慣用的繁體中文。只輸出譯文，不加任何說明。"
P_TITLE = "把下面這個英文維基百科條目標題翻成台灣慣用的繁體中文。人名、地名用台灣常見的譯名；沒有通行譯名的專有名詞用音譯；作品名直接翻譯，不加書名號。只輸出譯名。\n\n標題：{t}"
P_TEXT = ("把下面的英文{kind}翻成台灣慣用的繁體中文。\n規則：\n1. 專有名詞對照表裡的英文名稱只要出現在原文，譯文就必須寫成表裡的中文譯名：不可以換別的譯法，也不可以保留英文。\n2. 對照表裡沒有的人名、作品名、公司與機構名稱，保留英文原文，不要音譯。\n3. 不增加、不刪減內容；數字、年份照原文，月份與星期翻成中文。\n4. 只輸出譯文。\n\n"
          "專有名詞對照表：\n{gloss}\n\n英文{kind}：\n{text}")


class Gen:
    def __init__(self, base_url, tokenizer_json):
        import requests
        from tokenizers import Tokenizer

        self.url, self.tok, self._tls, self._rq = base_url, Tokenizer.from_file(tokenizer_json), threading.local(), requests
        self.in_tok = self.out_tok = 0
        self._lock = threading.Lock()

    def _s(self):
        if not hasattr(self._tls, "s"):
            self._tls.s = self._rq.Session()
        return self._tls.s

    def batch(self, users, max_new):
        ids = [self.tok.encode(TEMPLATE.format(sys=SYS, usr=u), add_special_tokens=False).ids for u in users]
        body = {"input_ids": ids, "sampling_params": {"max_new_tokens": max_new, "temperature": 0, "stop": ["<turn|>"]}}
        for attempt in range(4):
            try:
                r = self._s().post(self.url + "/generate", json=body, timeout=1800)
                r.raise_for_status()
                break
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(3)
        rs = r.json()
        rs = rs if isinstance(rs, list) else [rs]
        with self._lock:
            self.in_tok += sum(len(x) for x in ids)
            self.out_tok += sum(x["meta_info"].get("completion_tokens", 0) for x in rs)
        return [x["text"].replace("<turn|>", "").strip() for x in rs]

    def run(self, users, max_new, bs=32, workers=4, log=None, name=""):
        out = [None] * len(users)
        chunks = [list(range(i, min(i + bs, len(users)))) for i in range(0, len(users), bs)]
        t0 = time.time()

        def one(ch):
            for i, t in zip(ch, self.batch([users[i] for i in ch], max_new)):
                out[i] = t
            return len(ch)

        done = 0
        with ThreadPoolExecutor(workers) as ex:
            for n in ex.map(one, chunks):
                done += n
                if log and (done // bs) % 20 == 0:
                    log(f"  {name} {done}/{len(users)} ({time.time() - t0:.0f}s, out_tok {self.out_tok})")
        return out


def find_titles(text, by_first, max_n=20):
    """Titles (as whole words) that occur in `text`, longest first."""
    words = [(m.group(), m.start(), m.end()) for m in re.finditer(r"[^\W_]+", text)]
    hits, taken_until = [], -1
    for i, (w, s, _) in enumerate(words):
        if s < taken_until:
            continue
        for title, n in by_first.get(w, ()):  # candidates sorted longest first
            if i + n <= len(words) and text.startswith(title, s):
                e = s + len(title)
                if e == len(text) or not (text[e].isalnum()):
                    hits.append(title); taken_until = e
                    break
    return list(dict.fromkeys(hits))[:max_n]


def main(base_url, tokenizer_json, data_root, out_root, limit=0, log=print, commit=lambda: None):
    from opencc import OpenCC

    gen = Gen(base_url, tokenizer_json)
    corpus = [json.loads(l) for l in open(os.path.join(data_root, "musique", "corpus.jsonl"), encoding="utf-8")]
    questions = [json.loads(l) for l in open(os.path.join(data_root, "musique", "questions.jsonl"), encoding="utf-8")]
    qids = json.load(open(os.path.join(data_root, "musique", "splits.json")))["dev_zh_source"]
    if limit:
        corpus = corpus[:limit]
    tw_dir, cn_dir = os.path.join(out_root, "musique-zhtw"), os.path.join(out_root, "musique-zhcn")
    os.makedirs(tw_dir, exist_ok=True); os.makedirs(cn_dir, exist_ok=True)
    t0 = time.time()
    # ---- step 1: titles
    tm_path = os.path.join(out_root, "musique-title-map.json")
    tmap = json.load(open(tm_path, encoding="utf-8")) if os.path.exists(tm_path) else {}
    titles = [t for t in dict.fromkeys(c["title"] for c in corpus) if t and t not in tmap]
    if titles:
        res = gen.run([P_TITLE.format(t=t) for t in titles], 64, log=log, name="titles")
        for t, r in zip(titles, res):
            tmap[t] = r.splitlines()[0].strip().strip("《》「」") if r else t
        json.dump(tmap, open(tm_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
        commit()
    t_titles = time.time() - t0
    # a title with a trailing parenthetical ("Labyrinth (1984 video game)") is usually mentioned without it:
    # add the bare form as an alias, translated by stripping the parenthetical from the translated title too
    alias = {}
    for t, z in tmap.items():
        m = re.match(r"^(.*\S)\s*\([^)]*\)$", t)
        if m and m.group(1) not in tmap:
            zb = re.sub(r"\s*[\(（][^\)）]*[\)）]\s*$", "", z).strip()
            if zb:
                alias.setdefault(m.group(1), zb)
    tmap_all = dict(alias, **tmap)
    json.dump(alias, open(os.path.join(out_root, "musique-title-alias.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    by_first = {}
    for t in tmap_all:
        m = re.match(r"[^\W_]+", t)
        if m and len(t) >= 3:
            by_first.setdefault(m.group(), []).append((t, len(re.findall(r"[^\W_]+", t))))
    for v in by_first.values():
        v.sort(key=lambda x: -len(x[0]))

    # second pass: single-word titles that are frequent in running text are usually homographs of an ordinary word or a
    # different entity ("April", "Roman", "Queen", "Washington"); forcing their table entry mistranslates. Drop them
    # from the glossary unless the passage is that very article.
    use = {}
    for c in corpus:
        for t in find_titles(c["text"], by_first):
            use[t] = use.get(t, 0) + 1
    cal = set("January February March April May June July August September October November December Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split())
    drop = {t for t, n in use.items() if " " not in t and (n > 40 or t in cal)}
    json.dump(sorted(drop), open(os.path.join(out_root, "musique-gloss-dropped.json"), "w", encoding="utf-8"), ensure_ascii=False)
    log(f"glossary: dropped {len(drop)} ambiguous single-word entries")

    def prompt(kind, own_title, text):
        found = [t for t in find_titles(text, by_first) if t not in drop or t == own_title]   # names that literally occur in the source text
        ts = ([own_title] if own_title and own_title not in found else []) + found
        gloss = "\n".join(f"{t} = {tmap_all[t]}" for t in ts if t in tmap_all) or "（無）"
        return P_TEXT.format(kind=kind, gloss=gloss, text=text), [t for t in found if t in tmap_all]

    # ---- step 2: passages (resumable)
    part = os.path.join(out_root, "musique-zhtw.partial.v2.jsonl")
    done = {}
    if os.path.exists(part):
        for l in open(part, encoding="utf-8"):
            try:
                r = json.loads(l); done[r["pid"]] = r
            except Exception:  # noqa: BLE001
                pass
    todo = [c for c in corpus if c["pid"] not in done]
    log(f"passages to translate: {len(todo)} (already done {len(done)})")
    with open(part, "a", encoding="utf-8") as f:
        for i in range(0, len(todo), 1024):
            blk = todo[i:i + 1024]
            ps = [prompt("段落", c["title"], c["text"]) for c in blk]
            res = gen.run([p for p, _ in ps], 1536, log=log, name=f"passages[{i}]")
            for c, (_, gl), r in zip(blk, ps, res):
                row = {"pid": c["pid"], "title": tmap.get(c["title"], c["title"]), "text": r, "gloss": gl}
                done[c["pid"]] = row
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush(); os.fsync(f.fileno()); commit()
    # ---- step 3: questions
    qmap = {q["qid"]: q for q in questions}
    qp = [prompt("問題", None, qmap[q]["question"]) for q in qids]
    qres = gen.run([p for p, _ in qp], 256, log=log, name="questions")
    # ---- write datasets
    cc = OpenCC("tw2sp")
    for d, conv in ((tw_dir, lambda s: s), (cn_dir, cc.convert)):
        with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as f:
            for c in corpus:
                r = done[c["pid"]]
                f.write(json.dumps({"pid": r["pid"], "title": conv(r["title"]), "text": conv(r["text"])}, ensure_ascii=False) + "\n")
        with open(os.path.join(d, "questions.jsonl"), "w", encoding="utf-8") as f:
            for q, r in zip(qids, qres):
                f.write(json.dumps({"qid": q, "question": conv(r), "gold_pids": qmap[q]["gold_pids"], "type": qmap[q]["type"]}, ensure_ascii=False) + "\n")
        json.dump({"dev_zh": qids}, open(os.path.join(d, "splits.json"), "w"))
    # ---- consistency check over everything + a 50-passage sample for manual review
    tot = ok = 0
    for c in corpus:
        r = done[c["pid"]]
        for t in r["gloss"]:
            tot += 1
            ok += tmap_all[t] in r["text"]
    random.seed(20261110)
    sample = random.sample(corpus, min(50, len(corpus)))
    rows = []
    for c in sample:
        r = done[c["pid"]]
        rows.append({"pid": c["pid"], "title_en": c["title"], "title_zh": r["title"], "en": c["text"], "zh": r["text"],
                     "gloss": {t: tmap_all[t] for t in r["gloss"]}, "missing": [t for t in r["gloss"] if tmap_all[t] not in r["text"]]})
    qrows = [{"qid": q, "en": qmap[q]["question"], "zh": r, "gloss": {t: tmap_all[t] for t in gl}, "missing": [t for t in gl if tmap_all[t] not in r]} for q, (_, gl), r in zip(qids, qp, qres)]
    info = {"titles": len(tmap), "passages": len(corpus), "questions": len(qids), "titles_s": round(t_titles, 1), "total_s": round(time.time() - t0, 1),
            "in_tokens": gen.in_tok, "out_tokens": gen.out_tok, "gloss_terms": tot, "gloss_followed": ok, "consistency": ok / max(tot, 1),
            "empty": sum(1 for c in corpus if not done[c["pid"]]["text"]), "opencc": "tw2sp", "pass": 2, "gloss_dropped": len(drop)}
    json.dump({"info": info, "sample50": rows, "questions": qrows}, open(os.path.join(out_root, "musique-zh-spotcheck.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    commit()
    return info
