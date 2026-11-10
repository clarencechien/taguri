"""EG2 sidecar: runs in its own Python environment (EG2 needs a newer transformers than the SGLang image ships),
on the same GPU, and answers over localhost HTTP. Started by modal_taguri.py only for "+EG2" jobs.

  POST /build  {"db": <sqlite index path>, "out": <npy path>}  -> build info
  POST /search {"path": <npy path>, "query": str, "k": int}    -> {"rids": [...]}
"""
import json
import os
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taguri.dense import Dense  # noqa: E402

ENC = None
IDX = {}


class _Ix:  # the minimal part of taguri.index.Index that Dense.build needs
    def __init__(self, db):
        self.con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, check_same_thread=False)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        self._send({"ok": True, "load_s": ENC.load_s})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/build":
            out = ENC.build(_Ix(body["db"]), body["out"], limit=body.get("limit"))
        else:
            ix = IDX.get(body["path"])
            if ix is None:
                ix = IDX[body["path"]] = ENC.searcher(body["path"])
            out = {"rids": ix.search(body["query"], int(body.get("k", 20)))}
        self._send(out)

    def _send(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ENC = Dense(cache_dir=sys.argv[2] if len(sys.argv) > 2 else None, device=sys.argv[3] if len(sys.argv) > 3 else "cuda")
    print(f"EG2 loaded in {ENC.load_s:.1f}s", flush=True)
    ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
