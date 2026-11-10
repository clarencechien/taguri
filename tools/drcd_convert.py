"""Convert DRCD (official release, github.com/DRCKnowledgeTeam/DRCD) to the §5.1 layout for S7a.

  python tools/drcd_convert.py --src /path/to/DRCD --out /tmp/sag2poc-data

Writes <out>/drcd-tw/ (original Traditional Chinese) and <out>/drcd-cn/ (OpenCC tw2sp).
Corpus: every paragraph of training + dev + test (a larger pool separates the tokenisers better than the
test paragraphs alone). Questions: the test set; the single gold passage is the paragraph the question was
written for. The data files are NOT committed (DRCD is CC BY-SA 3.0; we keep only this script).
"""
import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    from opencc import OpenCC

    cc = OpenCC("tw2sp")
    corpus, questions = [], []
    for part in ("training", "dev", "test"):
        d = json.load(open(os.path.join(a.src, f"DRCD_{part}.json"), encoding="utf-8"))
        for art in d["data"]:
            for para in art["paragraphs"]:
                pid = str(para["id"])
                corpus.append({"pid": pid, "title": art["title"], "text": para["context"]})
                if part == "test":
                    for qa in para["qas"]:
                        questions.append({"qid": str(qa["id"]), "question": qa["question"], "gold_pids": [pid], "type": ""})
    assert len({c["pid"] for c in corpus}) == len(corpus)
    for name, conv in (("drcd-tw", lambda s: s), ("drcd-cn", cc.convert)):
        out = os.path.join(a.out, name)
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "corpus.jsonl"), "w", encoding="utf-8") as f:
            for c in corpus:
                f.write(json.dumps({"pid": c["pid"], "title": conv(c["title"]), "text": conv(c["text"])}, ensure_ascii=False) + "\n")
        with open(os.path.join(out, "questions.jsonl"), "w", encoding="utf-8") as f:
            for q in questions:
                f.write(json.dumps({**q, "question": conv(q["question"])}, ensure_ascii=False) + "\n")
        json.dump({"test": [q["qid"] for q in questions]}, open(os.path.join(out, "splits.json"), "w"))
    print({"passages": len(corpus), "questions": len(questions)})


if __name__ == "__main__":
    main()
