"""EG2 supplementary recall (handoff §7.2 Q2b). The ONLY place an embedding model is used.

- Document vectors are built once, stored as a float16 numpy matrix, and compared by brute force (no vector DB).
- EG2 scores only decide which passages ENTER the candidate set; they are never used for ranking the output.
- Task prompts follow the model card as used in jevlike (bench/embed_route.py):
    query:    "task: search result | query: {q}"
    document: "title: {title} | text: {text}"
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
    def __init__(self, cache_dir=None, device="cuda", max_seq_len=512):
        from sentence_transformers import SentenceTransformer

        t0 = time.time()
        self.model = SentenceTransformer(EG_MODEL, revision=EG_REV, device=device, cache_folder=cache_dir)
        self.model.max_seq_length = max_seq_len
        self.device = device
        self.load_s = time.time() - t0
        self._lock = threading.Lock()

    def encode(self, texts, batch_size=64):
        return np.asarray(self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False))

    def build(self, index, path, batch_size=64, limit=None, log=print):
        """Encode every passage of `index` (in rid order) and save float16 vectors to `path` (.npy)."""
        t0 = time.time()
        rows = index.con.execute("SELECT rid, title, text FROM passages ORDER BY rid" + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
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

    def searcher(self, path):
        return DenseIndex(self, path)


class DenseIndex:
    """One corpus' vectors on the model's device; brute-force dot product."""

    def __init__(self, enc: Dense, path):
        import torch

        self.enc = enc
        m = np.load(path)
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

    def __init__(self, port=30100):
        import requests

        self.url, self._s = f"http://127.0.0.1:{port}", requests.Session()
        self.load_s = self._s.get(self.url, timeout=30).json()["load_s"]

    def build(self, db_path, out, limit=None):
        return self._s.post(self.url + "/build", json={"db": db_path, "out": out, "limit": limit}, timeout=6 * 3600).json()

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
