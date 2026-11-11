"""S7 follow-up (option A): re-translate MuSiQue questions into zh-TW so that the names in a question match the passage
titles, and translate a separate Chinese calibration set.

Differences from tools/translate_musique.py step 3:
  - the glossary also offers titles that CONTAIN a capitalised word of the question ("Messi" -> "Lionel Messi = …"),
    as reference translations; the translator uses the matching part;
  - ambiguous single-word titles (musique-gloss-dropped.json) are not offered;
  - every name is rendered in Chinese (no English left in the question).
No gold labels are used. Writes four datasets under <out_root>:
  musique-zhtw2 / musique-zhcn2   translated corpus (unchanged) + new questions; splits dev_zh (100) and calib_zh (150)
  musique-xltw / musique-xlcn     ENGLISH corpus + the same Chinese questions (cross-lingual test)
"""
import json
import os
import re
import shutil

from tools.translate_musique import Gen, find_titles

P_Q = ("把下面的英文問題翻成台灣慣用的繁體中文。\n規則：\n1. 參考表列的是資料庫裡條目的既有中文譯名。問題裡的名稱如果就是表裡的某個條目，或是它的一部分"
       "（例如只寫姓氏），一律用表裡對應的中文寫法。\n2. 表裡沒有的人名、地名、作品名用台灣常見譯名或音譯，寫成中文，不要保留英文。\n3. 不增加、不刪減內容；只輸出譯文。\n\n"
       "參考表：\n{gloss}\n\n英文問題：\n{text}")
SKIP = set("What When Where Which Who Whom Whose Why How The In On At Of For And Is Are Was Were Did Does Do Has Have Had A An To By From With".split())


def main(base_url, tokenizer_json, data_root, out_root, log=print, commit=lambda: None):
    from opencc import OpenCC

    gen = Gen(base_url, tokenizer_json)
    tmap = json.load(open(os.path.join(out_root, "musique-title-map.json"), encoding="utf-8"))
    alias = json.load(open(os.path.join(out_root, "musique-title-alias.json"), encoding="utf-8"))
    drop = set(json.load(open(os.path.join(out_root, "musique-gloss-dropped.json"), encoding="utf-8")))
    T = {t: z for t, z in dict(alias, **tmap).items() if t not in drop and not z.isascii()}
    by_first, by_word = {}, {}
    for t in T:
        ws = re.findall(r"[^\W_]+", t)
        if ws and len(t) >= 3:
            by_first.setdefault(ws[0], []).append((t, len(ws)))
        for w in set(ws):
            if len(w) >= 3 and w[0].isupper():
                by_word.setdefault(w, []).append(t)
    for v in by_first.values():
        v.sort(key=lambda x: -len(x[0]))
    questions = {}
    for l in open(os.path.join(data_root, "musique", "questions.jsonl"), encoding="utf-8"):
        q = json.loads(l); questions[q["qid"]] = q
    splits = json.load(open(os.path.join(data_root, "musique", "splits.json")))
    sets = {"dev_zh": splits["dev_zh_source"], "calib_zh": splits["check"]}
    qids = sets["dev_zh"] + sets["calib_zh"]
    assert not set(sets["dev_zh"]) & set(sets["calib_zh"])

    def gloss_for(text):
        exact = find_titles(text, by_first)
        ref = list(exact)
        for w in re.findall(r"[^\W_]+", text):
            if w in SKIP or not w[0].isupper() or len(w) < 3:
                continue
            ts = [t for t in by_word.get(w, []) if t not in ref]
            if 0 < len(ts) <= 30:  # a word shared by many titles is not a name
                ref += sorted(ts, key=lambda t: (len(t), t))[:4]
        return exact, ref[:24]

    gl = [gloss_for(questions[q]["question"]) for q in qids]
    prompts = [P_Q.format(gloss="\n".join(f"{t} = {T[t]}" for t in ref) or "（無）", text=questions[q]["question"]) for q, (_, ref) in zip(qids, gl)]
    res = gen.run(prompts, 256, log=log, name="questions")
    cc = OpenCC("tw2sp")
    rows = []
    for q, (exact, ref), r in zip(qids, gl, res):
        rows.append({"qid": q, "en": questions[q]["question"], "zh": r, "exact": {t: T[t] for t in exact}, "n_ref": len(ref),
                     "missing": [t for t in exact if T[t] not in r], "latin": bool(re.search(r"[A-Za-z]{3,}", r))})
    zh = {x["qid"]: x["zh"] for x in rows}
    for name, corpus_src, conv in (("musique-zhtw2", os.path.join(out_root, "musique-zhtw", "corpus.jsonl"), lambda s: s),
                                   ("musique-zhcn2", os.path.join(out_root, "musique-zhcn", "corpus.jsonl"), cc.convert),
                                   ("musique-xltw", os.path.join(data_root, "musique", "corpus.jsonl"), lambda s: s),
                                   ("musique-xlcn", os.path.join(data_root, "musique", "corpus.jsonl"), cc.convert)):
        d = os.path.join(out_root, name)
        os.makedirs(d, exist_ok=True)
        shutil.copy(corpus_src, os.path.join(d, "corpus.jsonl"))
        with open(os.path.join(d, "questions.jsonl"), "w", encoding="utf-8") as f:
            for q in qids:
                f.write(json.dumps({"qid": q, "question": conv(zh[q]), "gold_pids": questions[q]["gold_pids"], "type": questions[q]["type"]}, ensure_ascii=False) + "\n")
        json.dump(sets, open(os.path.join(d, "splits.json"), "w"))
    n_exact = sum(len(x["exact"]) for x in rows)
    info = {"questions": len(qids), "exact_terms": n_exact, "exact_followed": n_exact - sum(len(x["missing"]) for x in rows),
            "with_latin_dev": sum(x["latin"] for x in rows[:len(sets["dev_zh"])]), "with_latin_calib": sum(x["latin"] for x in rows[len(sets["dev_zh"]):]),
            "in_tokens": gen.in_tok, "out_tokens": gen.out_tok}
    json.dump({"info": info, "rows": rows}, open(os.path.join(out_root, "musique-zh-questions-v2.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    commit()
    return info
