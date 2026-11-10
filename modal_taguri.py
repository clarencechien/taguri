"""Session B entry point on Modal: SGLang (Gemma 4 26B-A4B FP8, judge server, no MTP) and the engine in one container.

  export MODAL_TOKEN_ID=$modal MODAL_TOKEN_SECRET=$modal_secret
  modal run --detach modal_taguri.py --stage s6 --jobs '[{"config":"N1","dataset":"musique","split":"dev"}]'
  modal volume get taguri-b-results /s6 out/

SGLang image, launch flags and the L40S fused-MoE Triton config follow jevlike's modal_sglang.py.
The weights volume (gb10-decide-hf) is mounted read-only.
"""
import json
import os
import subprocess
import time
import urllib.request

import modal

MODEL_REPO, MODEL_REV = "RedHatAI/gemma-4-26B-A4B-it-FP8-dynamic", "ed35d7abe5d9"
GPU = os.environ.get("TAGURI_GPU", "L40S")
GPU_USD_PER_H = 1.95

app = modal.App("taguri-b")
weights = modal.Volume.from_name("gb10-decide-hf").read_only()
results = modal.Volume.from_name("taguri-b-results", create_if_missing=True)

image = (
    modal.Image.from_registry("lmsysorg/sglang:gemma4-mtp", add_python=None)
    .entrypoint([])
    .pip_install("jieba==0.42.1", "opencc-python-reimplemented==0.1.7", "snowballstemmer==3.1.1", "requests")
    .run_commands(
        "python3 - <<'PY'\n"
        "import json, os\n"
        "dirs=['/sgl-workspace/sglang/python/sglang/srt/layers/moe/fused_moe_triton/configs/triton_3_5_1',"
        "      '/sgl-workspace/sglang/python/sglang/srt/layers/moe/moe_runner/triton_utils/configs/triton_3_6_0']\n"
        "small={'BLOCK_SIZE_M':16,'BLOCK_SIZE_N':64,'BLOCK_SIZE_K':128,'GROUP_SIZE_M':1,'num_warps':4,'num_stages':3}\n"
        "big={'BLOCK_SIZE_M':64,'BLOCK_SIZE_N':64,'BLOCK_SIZE_K':128,'GROUP_SIZE_M':8,'num_warps':4,'num_stages':3}\n"
        "cfg={str(m):(small if m<=32 else big) for m in [1,2,4,8,16,24,32,48,64,96,128,256,512,1024,1536,2048,3072,4096]}\n"
        "for d in dirs:\n"
        "  os.makedirs(d, exist_ok=True)\n"
        "  for n in ['E=128,N=704,device_name=NVIDIA_L40S,dtype=fp8_w8a8,per_channel_quant=True.json','E=128,N=704,device_name=NVIDIA_L40S,dtype=fp8_w8a8,per_channel_quant=True_down.json']:\n"
        "    json.dump(cfg, open(os.path.join(d,n),'w'), indent=1)\n"
        "print('wrote moe configs')\n"
        "PY"
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "0"})
)


def _with_code(img):
    return (img.add_local_dir("taguri", remote_path="/root/taguri")
            .add_local_dir("evalkit", remote_path="/root/evalkit")
            .add_local_dir("data", remote_path="/root/data")
            .add_local_file("results/thresholds.lock.json", remote_path="/root/results/thresholds.lock.json"))


base_image = image
image = _with_code(base_image)
# EG2 (N4 and "+EG2" groups only) needs sentence-transformers; kept in a separate image so the judge-only runs are untouched.
image_eg = _with_code(base_image.run_commands(
    "python3 -m venv /opt/eg && /opt/eg/bin/pip install -q torch torchvision torchaudio pillow requests 'sentence-transformers>=6.1.0' 'transformers>=5.19.0' numpy"))


def start_server(port=30000, ctx=16384, max_running=64, extra=()):
    cmd = ["python3", "-m", "sglang.launch_server", "--model-path", f"/hf/{MODEL_REPO}", "--context-length", str(ctx),
           "--max-running-requests", str(max_running), "--mem-fraction-static", os.environ.get("SGL_MEM_FRACTION", "0.8"), "--host", "127.0.0.1", "--port", str(port),
           "--log-level", "warning", *extra]
    print("starting:", " ".join(cmd), flush=True)
    t0 = time.time()
    proc = subprocess.Popen(cmd)
    for _ in range(1800):
        if proc.poll() is not None:
            raise RuntimeError(f"sglang exited early {proc.returncode}")
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
            print(f"sglang healthy after {time.time() - t0:.1f}s", flush=True)
            return proc, time.time() - t0
        except Exception:  # noqa: BLE001
            time.sleep(1)
    proc.terminate()
    raise RuntimeError("sglang not healthy")


@app.function(image=image, gpu=GPU, volumes={"/hf": weights, "/results": results}, timeout=60 * 60 * 4)
def run(stage: str, jobs: str, run_id: str = ""):
    return _run(stage, jobs, run_id)


@app.function(image=image_eg, gpu=GPU, volumes={"/hf": weights, "/results": results}, timeout=60 * 60 * 6)
def run_eg(stage: str, jobs: str, run_id: str = ""):
    os.environ["SGL_MEM_FRACTION"] = "0.72"  # leave room on the same GPU for the EG2 sidecar
    os.environ["EG2_DEVICE"] = "cuda"
    return _run(stage, jobs, run_id)


def _run(stage: str, jobs: str, run_id: str = ""):
    """jobs: JSON list of {"config", "dataset", "split", "lang"?, "tag"?, "limit"?, "tau"?, "out_mode"?, "data_root"?, "doc_level"?}"""
    import sys

    sys.path.insert(0, "/root")
    t_container = time.time()
    from taguri.analyze import Analyzer
    from taguri.decide import LLMDecider, SGLangBackend
    from taguri.pipeline import Engine
    from taguri.run import get_index, load_lock, make_config, run_split
    from evalkit import aggregate, load_questions, load_split, score_run

    jobs = json.loads(jobs)
    run_id = run_id or time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    lock = load_lock("/root/results/thresholds.lock.json")
    need_gpu = any(j.get("probe") or make_config(j["config"], lock).judge for j in jobs)
    proc, t_start = (start_server() if need_gpu else (None, 0.0))
    smi = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used", "--format=csv,noheader"], capture_output=True, text=True).stdout.strip()
    env = {"run_id": run_id, "gpu": smi, "server_start_s": round(t_start, 1), "model": MODEL_REPO, "rev": MODEL_REV, "jobs": jobs}
    out_root = f"/results/{stage}"
    os.makedirs(out_root, exist_ok=True)
    report = []
    eg_proc = None
    try:
        backend = SGLangBackend("http://127.0.0.1:30000", f"/hf/{MODEL_REPO}/tokenizer.json", cache_dir="/results/cache", run_id=run_id) if need_gpu else None
        if backend:
            print(f"judge cache: {backend.loaded} entries", flush=True)

        def flush():
            if backend:
                backend.flush()
            results.commit()

        analyzers, indexes, dense_ix = {}, {}, {}
        encoder = None
        for j in jobs:
            t_job = time.time()
            if j.get("probe"):
                from taguri.probe import run_probe

                row = run_probe(j, backend, lock, f"{out_root}/{j['tag']}", flush)
                print(json.dumps(row), flush=True)
                report.append(row)
                continue
            ds, split, lang = j["dataset"], j.get("split", "dev"), j.get("lang", "en")
            data_root = j.get("data_root", "/root/data")
            zh_key = j.get("zh_key", lock.get("zh_key", "tw2sp"))
            an = analyzers.setdefault(zh_key, Analyzer(zh_key=zh_key))
            ikey = (data_root, ds, zh_key)
            if ikey not in indexes:
                indexes[ikey] = get_index(ds, data_root, "/tmp/idx" + data_root.replace("/", "_"), an, lock.get("weights"), tag=f"-{zh_key}",
                                          doc_field=j.get("doc_field"))
            ix = indexes[ikey]
            if j.get("debug_lowmass") and backend:
                backend.debug_dir = f"{out_root}/{j['tag']}"
                os.makedirs(backend.debug_dir, exist_ok=True)
            cfg = make_config(j["config"], lock, tau=j.get("tau"), out_mode=j.get("out_mode"), rounds=j.get("rounds"), beta=j.get("beta"), chunk=j.get("chunk"), rejudge=j.get("rejudge"), bridge=j.get("bridge"), adaptive=j.get("adaptive"), rejudge_each=j.get("rejudge_each"), pick_none=j.get("pick_none"), min_pool=j.get("min_pool"), term_rank=j.get("term_rank"), n_cand=j.get("n_cand"), m=j.get("m"), K=j.get("K"))
            questions = load_questions(ds, data_root)
            qids = load_split(ds, split, data_root)
            if j.get("limit"):
                qids = qids[: int(j["limit"])]
            dense = None
            if cfg.dense:
                if encoder is None:
                    from taguri.dense import DenseClient

                    eg_proc = subprocess.Popen(["/opt/eg/bin/python", "/root/taguri/dense_server.py", "30100", "/results/hf", os.environ.get("EG2_DEVICE", "cpu")])
                    for _ in range(900):
                        if eg_proc.poll() is not None:
                            raise RuntimeError("EG2 sidecar exited")
                        try:
                            encoder = DenseClient(30100)
                            break
                        except Exception:  # noqa: BLE001
                            time.sleep(1)
                    env["eg2_load_s"] = round(encoder.load_s, 1)
                    results.commit()
                if ikey not in dense_ix:
                    os.makedirs("/results/dense", exist_ok=True)
                    vec = f"/results/dense/{data_root.strip('/').replace('/', '_')}-{ds}.npy"
                    if not os.path.exists(vec):
                        info = encoder.build(ix.db_path, vec)
                        print("EG2 vectors:", json.dumps(info), flush=True)
                        results.commit()
                    dense_ix[ikey] = encoder.searcher(vec)
                    env.setdefault("eg2", {})[ds] = json.load(open(vec + ".json"))
                dense = dense_ix[ikey]
            eng = Engine(ix, LLMDecider(backend, lang, j.get("q3", lock.get("q3_variant", "A")), j.get("layout", lock.get("layout", "L1"))) if cfg.judge else None,
                         dense=dense, doc_level=bool(j.get("doc_level")))
            tag = j.get("tag") or f"{ds}-{split}-{j['config']}"
            out_dir = f"{out_root}/{tag}"
            summ = run_split(eng, cfg, questions, qids, out_dir, workers=int(j.get("workers", 16)), flush=flush)
            run_rows = {json.loads(l)["qid"]: json.loads(l)["retrieved"] for l in open(f"{out_dir}/run.jsonl")}
            agg = aggregate(score_run(questions, run_rows, qids))
            if dense is not None:
                summ["eg2_query_s"] = round(dense.query_s, 2); summ["eg2_queries"] = dense.queries
                json.dump(summ, open(f"{out_dir}/summary.json", "w"), indent=1)
                dense.query_s, dense.queries = 0.0, 0
            row = {"tag": tag, "job_s": round(time.time() - t_job, 1), "calls_median": summ["calls_median"], "fresh_calls": summ["fresh_calls"],
                   "fresh_tokens": summ["fresh_tokens"], "min_mass": summ["min_option_mass"], **{k: round(v, 2) for k, v in agg.items()}}
            print(json.dumps(row), flush=True)
            report.append(row)
            env["report"] = report
            env["container_s"] = round(time.time() - t_container, 1)
            env["est_usd"] = round(env["container_s"] * GPU_USD_PER_H / 3600, 3)
            json.dump(env, open(f"{out_root}/_run_{run_id}.json", "w"), indent=1)
            flush()
    finally:
        if proc:
            proc.terminate()
        if eg_proc:
            eg_proc.terminate()
        env["container_s"] = round(time.time() - t_container, 1)
        env["est_usd"] = round(env["container_s"] * GPU_USD_PER_H / 3600, 3)
        env["done"] = True
        json.dump(env, open(f"{out_root}/_run_{run_id}.json", "w"), indent=1)
        results.commit()
    return env


@app.local_entrypoint()
def main(stage: str = "smoke", jobs: str = "[]", run_id: str = "", eg: bool = False):
    env = (run_eg if eg else run).remote(stage, jobs, run_id)
    print(json.dumps(env, indent=1, ensure_ascii=False)[:8000])
