"""S10 data preparation: EnterpriseRAG-Bench (Hugging Face onyx-dot-app/EnterpriseRAG-Bench) -> §5.1 layout.

Chunking (handoff §7.1 item 4): a document of at most 2,000 characters is one passage; a longer one is cut at
paragraph boundaries into passages of at most 2,000 characters. `title` = "<document title> [<source type>]".
Scoring is per document: every passage row carries `doc`, and the engine de-duplicates by it.
Questions: the 470 that have recall labels (expected_doc_ids non-empty and type not high_level / info_not_found).
"""
import json
import os
import re

REPO, REV = "onyx-dot-app/EnterpriseRAG-Bench", "69916e31c68aa5963c00248fd7f0bc12d04fd235"
MAX = 2000


def chunk(text, limit=MAX):
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        pieces = [para]
        if len(para) > limit:  # a single oversized paragraph: fall back to lines, then to hard cuts
            pieces = []
            buf = ""
            for line in para.split("\n"):
                while len(line) > limit:
                    cut = line.rfind(" ", 0, limit)
                    cut = cut if cut > limit // 2 else limit
                    if buf:
                        pieces.append(buf); buf = ""
                    pieces.append(line[:cut]); line = line[cut:].lstrip()
                if len(buf) + len(line) + 1 > limit:
                    pieces.append(buf); buf = line
                else:
                    buf = (buf + "\n" + line) if buf else line
            if buf:
                pieces.append(buf)
        for p in pieces:
            if len(cur) + len(p) + 2 > limit:
                if cur:
                    out.append(cur)
                cur = p
            else:
                cur = (cur + "\n\n" + p) if cur else p
    if cur:
        out.append(cur)
    return out


def main(out_dir, cache_dir=None, log=print):
    import pyarrow.parquet as pq
    from huggingface_hub import hf_hub_download

    os.makedirs(out_dir, exist_ok=True)
    qf = hf_hub_download(REPO, "data/questions/test.parquet", repo_type="dataset", revision=REV, cache_dir=cache_dir)
    df = hf_hub_download(REPO, "data/documents/test.parquet", repo_type="dataset", revision=REV, cache_dir=cache_dir)
    qs = pq.read_table(qf).to_pylist()
    kept, types = [], {}
    with open(os.path.join(out_dir, "questions.jsonl"), "w", encoding="utf-8") as f:
        for q in qs:
            gold = list(q.get("expected_doc_ids") or [])
            types[q["question_type"]] = types.get(q["question_type"], 0) + 1
            if not gold or q["question_type"].lower().replace(" ", "_") in ("high_level", "info_not_found"):
                continue
            kept.append(q["question_id"])
            f.write(json.dumps({"qid": q["question_id"], "question": q["question"], "gold_pids": gold, "type": q["question_type"]}, ensure_ascii=False) + "\n")
    json.dump({"recall470": kept}, open(os.path.join(out_dir, "splits.json"), "w"))
    n_doc = n_pas = n_long = chars = n_dup = 0
    seen = set()
    src = {}
    pf = pq.ParquetFile(df)
    with open(os.path.join(out_dir, "corpus.jsonl"), "w", encoding="utf-8") as f:
        for batch in pf.iter_batches(batch_size=5000):
            for d in batch.to_pylist():
                if d["doc_id"] in seen:  # the release repeats a few doc_ids: keep the first copy
                    n_dup += 1
                    continue
                seen.add(d["doc_id"])
                n_doc += 1
                src[d["source_type"]] = src.get(d["source_type"], 0) + 1
                parts = chunk(d.get("content") or "")
                n_long += len(parts) > 1
                title = f"{d.get('title') or ''} [{d['source_type']}]"
                for i, p in enumerate(parts or [""]):
                    n_pas += 1; chars += len(p)
                    f.write(json.dumps({"pid": f"{d['doc_id']}#{i}", "doc": d["doc_id"], "title": title, "text": p}, ensure_ascii=False) + "\n")
            if n_doc % 50000 < 5000:
                log(f"  {n_doc} docs -> {n_pas} passages")
    info = {"repo": REPO, "rev": REV, "dedup": True, "duplicate_doc_id_rows": n_dup, "documents": n_doc, "passages": n_pas, "split_documents": n_long, "chars": chars, "questions_total": len(qs),
            "questions_kept": len(kept), "question_types": types, "sources": src}
    json.dump(info, open(os.path.join(out_dir, "MANIFEST.json"), "w"), indent=1)
    return info
