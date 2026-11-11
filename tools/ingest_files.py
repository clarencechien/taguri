"""Turn a folder of text files into a Taguri corpus (corpus.jsonl) and its SQLite index. Offline, CPU only.

  python tools/ingest_files.py --src /path/to/docs --out /path/to/store --name mydocs

Reads .txt / .md / .markdown / .log / .csv / .json / .html-as-text files recursively (UTF-8; undecodable bytes are replaced).
Other formats (PDF, Word, Excel) must be converted to text first; this tool does not parse them.
Each file is one document; a document longer than 2,000 characters is cut at paragraph boundaries (same rule as
tools/enterprise_prep.py). `title` = "<first heading or file name> [<relative path>]", `doc` = relative path.

Writes  <out>/<name>/corpus.jsonl     the passages
        <out>/<name>/MANIFEST.json    counts
        <out>/idx/<name>.db           SQLite FTS5 index (also holds the passage text)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taguri.analyze import Analyzer  # noqa: E402
from taguri.index import build  # noqa: E402
from tools.enterprise_prep import chunk  # noqa: E402

EXT = {".txt", ".md", ".markdown", ".log", ".csv", ".json", ".html", ".htm", ".rst"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    a = ap.parse_args()
    lock_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "results", "thresholds.lock.json")
    lock = json.load(open(lock_path)) if os.path.exists(lock_path) else {}
    d = os.path.join(a.out, a.name)
    os.makedirs(d, exist_ok=True); os.makedirs(os.path.join(a.out, "idx"), exist_ok=True)
    n_doc = n_pas = skipped = 0
    with open(os.path.join(d, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for root, _, files in os.walk(a.src):
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in EXT:
                    skipped += 1
                    continue
                path = os.path.join(root, fn)
                rel = os.path.relpath(path, a.src)
                text = open(path, encoding="utf-8", errors="replace").read()
                m = re.search(r"^\s*#+\s*(.+)$", text, re.M)
                title = f"{(m.group(1).strip() if m else os.path.splitext(fn)[0])[:120]} [{rel}]"
                n_doc += 1
                for i, p in enumerate(chunk(text) or [""]):
                    n_pas += 1
                    f.write(json.dumps({"pid": f"{rel}#{i}", "doc": rel, "title": title, "text": p}, ensure_ascii=False) + "\n")
    db = os.path.join(a.out, "idx", f"{a.name}.db")
    info = build(os.path.join(d, "corpus.jsonl"), db, Analyzer(zh_key=lock.get("zh_key", "tw2sp")), doc_field="doc", workers=a.workers)
    man = {"documents": n_doc, "passages": n_pas, "skipped_files": skipped, "index": info, "db": db}
    json.dump(man, open(os.path.join(d, "MANIFEST.json"), "w"), indent=1)
    print(json.dumps(man, ensure_ascii=False))


if __name__ == "__main__":
    main()
