"""Where does the lexical layer's English edge go in Chinese? (TODO B10; CPU only, no judge.)

For each language of the dev-zh 100 questions: N0 with the locked settings, then with the title/id anchors off,
with the title field weight set to 1, and with both off; plus how often the anchors fire and how often they hit gold.

usage: zh_lexical_diag.py <data root with musique-zhtw2/ musique-zhcn2/> <index dir>
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from evalkit import load_questions, load_split, score_run
from evalkit.bootstrap import paired_bootstrap
from taguri.analyze import Analyzer
from taguri.pipeline import Config, Engine
from taguri.run import get_index, load_lock

ROOT, IDX = sys.argv[1], sys.argv[2]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
lock = load_lock(os.path.join(REPO, "results", "thresholds.lock.json"))
an = Analyzer(zh_key=lock.get("zh_key", "tw2sp"))
LANGS = [("英文", "musique", os.path.join(REPO, "data"), "dev_zh_source"), ("繁中", "musique-zhtw2", ROOT, "dev_zh"), ("簡中", "musique-zhcn2", ROOT, "dev_zh")]
W = dict(lock["weights"]); W1 = dict(W, title=1.0)
VARIANTS = [("定案（標題權重 4，錨定加分 3）", W, lock["anchor_bonus"]), ("關掉錨定", W, 0.0), ("標題權重改 1", W1, lock["anchor_bonus"]), ("兩個都關", W1, 0.0),
            ("兩個都關，只用字元 bigram", dict(W1, cjk_word=0.0), 0.0), ("兩個都關，只用詞", dict(W1, cjk_bigram=0.0), 0.0)]

scores, stats = {}, {}
for lang, ds, root, split in LANGS:
    qs = load_questions(ds, root); qids = load_split(ds, split, root)
    for name, w, bonus in VARIANTS:
        ix = get_index(ds, root, IDX, an, w, tag="-tw2sp", log=lambda *a: None)
        eng = Engine(ix, None)
        run = {q: eng.run(qs[q], Config(name="N0", anchor_bonus=bonus))["retrieved"] for q in qids}
        scores[lang, name] = score_run(qs, run, qids)
    ix = get_index(ds, root, IDX, an, W, tag="-tw2sp", log=lambda *a: None)
    n_q = n_a = n_title = n_id = q_gold = gold_hit = gold_all = a_gold = 0
    for q in qids:
        gold = {ix.rid_of(p) for p in qs[q]["gold_pids"]}
        anchors = ix.anchors(qs[q]["question"])
        rids = set()
        for a in anchors:
            n_title += a["kind"] == "title"; n_id += a["kind"] == "id"
            a_gold += bool(gold & set(a["rids"])); rids |= set(a["rids"])
        n_q += bool(anchors); n_a += len(anchors); q_gold += bool(gold & rids)
        gold_hit += len(gold & rids); gold_all += len(gold)
    n = len(qids)
    stats[lang] = {"有錨定的題目": f"{100 * n_q / n:.0f}%", "每題錨定數": f"{n_a / n:.2f}", "其中標題／編號": f"{n_title}／{n_id}",
                   "錨定指到金標的比例": f"{100 * a_gold / max(n_a, 1):.0f}%", "至少一個錨定指到金標的題目": f"{100 * q_gold / n:.0f}%",
                   "被錨定指到的金標段落": f"{100 * gold_hit / gold_all:.1f}%"}

langs = [l[0] for l in LANGS]


def mean(s, m="R@5"):
    return 100 * sum(v[m] for v in s.values()) / len(s)


print("| N0 的 R@5 | " + " | ".join(langs) + " |\n|---|" + "---:|" * len(langs))
for name, _, _ in VARIANTS:
    print(f"| {name} | " + " | ".join(f"{mean(scores[l, name]):.2f}" for l in langs) + " |")
base = VARIANTS[0][0]
print("\n| 定案 − 變體（ΔR@5） | " + " | ".join(langs) + " |\n|---|" + "---|" * len(langs))
for name, _, _ in VARIANTS[1:]:
    cells = []
    for l in langs:
        r = paired_bootstrap(scores[l, base], scores[l, name], metric="R@5")
        cells.append(f"{r['delta']:+.2f}（{r['ci_low']:+.2f}，{r['ci_high']:+.2f}）")
    print(f"| {name} | " + " | ".join(cells) + " |")
print("\n| 錨定 | " + " | ".join(langs) + " |\n|---|" + "---:|" * len(langs))
for k in stats[langs[0]]:
    print(f"| {k} | " + " | ".join(stats[l][k] for l in langs) + " |")
json.dump({f"{l}|{n}": mean(s) for (l, n), s in scores.items()}, open(os.path.join(IDX, "zh_lexical_diag.json"), "w"), ensure_ascii=False, indent=1)

# ---- which CJK field(s): locked features on, on the dev-zh 100 and on the separate Chinese calibration 150
FIELDS = [("兩個欄位都開（定案）", W), ("只用字元 bigram", dict(W, cjk_word=0.0)), ("只用詞", dict(W, cjk_bigram=0.0))]
print("\n| 中文欄位（標題權重 4，錨定加分 3），R@5／R@10 | 繁中 dev-zh 100 題 | 繁中校準 150 題 | 簡中 dev-zh 100 題 | 簡中校準 150 題 |\n|---|---|---|---|---|")
res = {}
for ds in ("musique-zhtw2", "musique-zhcn2"):
    qs = load_questions(ds, ROOT)
    for split in ("dev_zh", "calib_zh"):
        qids = load_split(ds, split, ROOT)
        for name, w in FIELDS:
            eng = Engine(get_index(ds, ROOT, IDX, an, w, tag="-tw2sp", log=lambda *a: None), None)
            res[ds, split, name] = score_run(qs, {q: eng.run(qs[q], Config(name="N0", anchor_bonus=lock["anchor_bonus"]))["retrieved"] for q in qids}, qids)
cols = [(d, s) for d in ("musique-zhtw2", "musique-zhcn2") for s in ("dev_zh", "calib_zh")]
for name, _ in FIELDS:
    print(f"| {name} | " + " | ".join(f"{mean(res[d, s, name]):.2f}／{mean(res[d, s, name], 'R@10'):.2f}" for d, s in cols) + " |")
for name, _ in FIELDS[1:]:
    cells = []
    for d, s in cols:
        r = paired_bootstrap(res[d, s, name], res[d, s, FIELDS[0][0]], metric="R@5")
        cells.append(f"{r['delta']:+.2f}（{r['ci_low']:+.2f}，{r['ci_high']:+.2f}）")
    print(f"| {name} − 定案（ΔR@5） | " + " | ".join(cells) + " |")
