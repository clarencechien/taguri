"""EG2 supplementary recall (handoff §7.2 Q2b). The ONLY place an embedding model is used.

- Document vectors are built once, stored as a float16 numpy matrix, and compared by brute force (no vector DB).
- EG2 scores only decide which passages ENTER the candidate set; they are never used for ranking the output.
- Task prompts follow the model card as used in jevlike (bench/embed_route.py):
    query:    "task: search result | query: {q}"
    document: "title: {title} | text: {text}"

Build the vectors of an index once (the model can be a local directory, for machines without network access):

  python -m taguri.dense build --db store/idx/mydocs.db --out store/idx/mydocs.eg2.npy \
      --model /models/embeddinggemma-2 --device cuda

then pass --dense-vectors / --eg2-model to taguri.run or taguri.query.
"""
from __future__ import annotations

import json
import os
import threading
import time

import numpy as np

EG_MODEL, EG_REV = "google/embeddinggemma-2", "914f7f89142e33e77833254d9c9b90c3cef7303b"
QRY = "task: search result | query: "


def doc_text(title, text):
    return f"title: {title or 'none'} | text: {text}"


class Dense:
    def __init__(self, cache_dir=None, device="cuda", max_seq_len=512, model=None):
        """model: a local directory holding the model files, or None for the pinned Hugging Face revision."""
        from sentence_transformers import SentenceTransformer

        t0 = time.time()
        if model and os.path.isdir(model):
            self.model = SentenceTransformer(model, device=device)
        else:
            self.model = SentenceTransformer(model or EG_MODEL, revision=None if model else EG_REV, device=device, cache_folder=cache_dir)
        self.model.max_seq_length = max_seq_len
        self.device = device
        self.load_s = time.time() - t0
        self._lock = threading.Lock()

    def encode(self, texts, batch_size=64):
        return np.asarray(self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False))

    def build(self, index, path, batch_size=64, limit=None, log=print, start=0, stop=None):
        """Encode passages of `index` in rid order (optionally only start < rid <= stop) and save float16 vectors to `path` (.npy)."""
        t0 = time.time()
        where = f" WHERE rid > {int(start)}" + (f" AND rid <= {int(stop)}" if stop else "")
        rows = index.con.execute("SELECT rid, title, text FROM passages" + where + " ORDER BY rid" + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
        out = None
        for i in range(0, len(rows), 4096):
            part = rows[i:i + 4096]
            v = self.encode([doc_text(t, x) for _, t, x in part], batch_size).astype(np.float16)
            if out is None:
                out = np.zeros((len(rows), v.shape[1]), dtype=np.float16)
            out[i:i + len(part)] = v
            if (i // 4096) % 10 == 0:
                log(f"  EG2 encoded {i + len(part)}/{len(rows)} ({time.time() - t0:.0f}s)")
        info = {"n": len(rows), "dim": int(out.shape[1]), "build_s": round(time.time() - t0, 1), "bytes": int(out.nbytes), "model": EG_MODEL, "rev": EG_REV}
        if path:
            np.save(path, out)
            json.dump(info, open(path + ".json", "w"))
        return info

    def searcher(self, path, expect_n=None):
        return DenseIndex(self, path, expect_n)


class DenseIndex:
    """One corpus' vectors on the model's device; brute-force dot product."""

    def __init__(self, enc: Dense, path, expect_n=None):
        import torch

        self.enc = enc
        m = np.load(path)
        if expect_n is not None and m.shape[0] != expect_n:
            raise ValueError(f"{path} has {m.shape[0]} vectors but the index has {expect_n} passages: the vectors were built from a different index")
        self.M = torch.from_numpy(m).to(enc.device)
        if enc.device == "cpu":
            self.M = self.M.float()
        self.shape = m.shape
        self._qcache = {}
        self.query_s, self.queries = 0.0, 0

    def search(self, query, k=20):
        """-> rids (1-based row ids of the index) of the k nearest passages."""
        import torch

        with self.enc._lock:
            hit = self._qcache.get((query, k))
            if hit is not None:
                return hit
            t0 = time.perf_counter()
            q = torch.from_numpy(self.enc.encode([QRY + query])[0]).to(self.enc.device).to(self.M.dtype)
            top = torch.topk(self.M @ q, min(k, self.M.shape[0])).indices.tolist()
            out = [i + 1 for i in top]
            self._qcache[(query, k)] = out
            self.query_s += time.perf_counter() - t0
            self.queries += 1
            return out


class DenseClient:
    """Talks to taguri/dense_server.py (EG2 in its own Python environment)."""

    def __init__(self, port=30100, url=None):
        import requests

        self.url, self._s = (url or f"http://127.0.0.1:{port}").rstrip("/"), requests.Session()
        self.load_s = self._s.get(self.url, timeout=30).json()["load_s"]

    def build(self, db_path, out, limit=None, start=0, stop=None):
        return self._s.post(self.url + "/build", json={"db": db_path, "out": out, "limit": limit, "start": start, "stop": stop}, timeout=6 * 3600).json()

    def searcher(self, path):
        return _ClientIndex(self, path)


class _ClientIndex:
    def __init__(self, c, path):
        self.c, self.path = c, path
        self._qcache, self._lock = {}, threading.Lock()
        self.query_s, self.queries = 0.0, 0

    def search(self, query, k=20):
        import requests

        with self._lock:
            hit = self._qcache.get((query, k))
        if hit is not None:
            return hit
        t0 = time.perf_counter()
        out = requests.post(self.c.url + "/search", json={"path": self.path, "query": query, "k": k}, timeout=600).json()["rids"]
        with self._lock:
            self._qcache[(query, k)] = out
            self.query_s += time.perf_counter() - t0
            self.queries += 1
        return out


def open_dense(vectors, model=None, device="cpu", url=None, expect_n=None, cache_dir=None):
    """The object the pipeline needs (`.search(query, k) -> rids`). url: a running taguri/dense_server.py
    (EG2 in another Python environment); otherwise the model is loaded in this process."""
    if not os.path.exists(vectors):
        raise FileNotFoundError(f"{vectors}: build it first with  python -m taguri.dense build --db <index.db> --out {vectors}")
    if url:
        return DenseClient(url=url).searcher(vectors)
    return Dense(cache_dir=cache_dir, device=device, model=model).searcher(vectors, expect_n)


def main():
    import argparse
    import sqlite3

    ap = argparse.ArgumentParser(description="Build EG2 vectors for an index (one row per passage, in rid order).")
    ap.add_argument("cmd", choices=["build"])
    ap.add_argument("--db", required=True, help="the SQLite index built by taguri.run or tools/ingest_files.py")
    ap.add_argument("--out", required=True, help="output .npy (float16, n x 768)")
    ap.add_argument("--model", help="local model directory; default: the pinned Hugging Face revision")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--limit", type=int, help="only the first N passages (timing test)")
    a = ap.parse_args()

    class _Ix:
        con = sqlite3.connect(f"file:{a.db}?mode=ro", uri=True)

    enc = Dense(device=a.device, model=a.model)
    print(json.dumps(enc.build(_Ix, a.out, batch_size=a.batch, limit=a.limit)))


if __name__ == "__main__":
    main()
